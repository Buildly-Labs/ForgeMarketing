#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

export SKIP_STARTUP_DB_INIT=1
BASELINE_REVISION="${MARKETING_BASELINE_REVISION:-0d6491da3ab7}"

# Use one interpreter consistently for all migration/bootstrap commands.
# This avoids mismatches where `python3` points to a different environment
# than the one used to install app dependencies.
PYTHON_BIN="${PYTHON_BIN:-python}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="python3"
    else
        echo "No usable Python interpreter found (tried '$PYTHON_BIN' and 'python3')."
        exit 1
    fi
fi

echo "Running marketing database migrations..."
echo "Using Python interpreter: $(command -v "$PYTHON_BIN")"

# If a legacy schema exists without Alembic tracking, stamp it once.
set +e
"$PYTHON_BIN" - <<'PY'
from dashboard.app import app
from dashboard.models import db
from sqlalchemy import inspect

with app.app_context():
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())
    has_alembic_version = 'alembic_version' in tables
    has_existing_schema = any(name in tables for name in {'brands', 'users', 'system_configs'})

    if has_existing_schema and not has_alembic_version:
        raise SystemExit(10)

raise SystemExit(0)
PY
status=$?
set -e

if [[ $status -eq 10 ]]; then
    echo "Legacy schema detected without alembic_version; stamping baseline ${BASELINE_REVISION}."
    "$PYTHON_BIN" -m flask --app dashboard.app:app db stamp "$BASELINE_REVISION"
elif [[ $status -ne 0 ]]; then
    echo "Failed to inspect schema state before migration."
    exit $status
fi

set +e
upgrade_output=$("$PYTHON_BIN" -m flask --app dashboard.app:app db upgrade 2>&1)
upgrade_status=$?
set -e

if [[ $upgrade_status -ne 0 ]]; then
    echo "$upgrade_output"
    if echo "$upgrade_output" | grep -qi "Can't locate revision identified by"; then
        echo "Unknown Alembic revision found; stamping current head and retrying upgrade."
        "$PYTHON_BIN" -m flask --app dashboard.app:app db stamp head
        "$PYTHON_BIN" -m flask --app dashboard.app:app db upgrade
    else
        echo "Marketing database migration failed."
        exit $upgrade_status
    fi
else
    echo "$upgrade_output"
fi

# Lead Radar and other runtime tables are defined in SQLAlchemy models but are
# not yet fully represented in Alembic revisions. Ensure they exist.
"$PYTHON_BIN" - <<'PY'
from dashboard.app import app
from dashboard.models import db
from dashboard import lead_radar_models  # noqa: F401
from dashboard import marketing_calendar_models  # noqa: F401

with app.app_context():
    db.create_all()
    print("Ensured runtime SQLAlchemy tables exist (including Lead Radar).")
PY

"$PYTHON_BIN" "$PROJECT_ROOT/ops/verify_marketing_schema.py"

echo "Marketing database migrations complete."
