#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

export SKIP_STARTUP_DB_INIT=1
BASELINE_REVISION="${MARKETING_BASELINE_REVISION:-0d6491da3ab7}"

echo "Running marketing database migrations..."

# If a legacy schema exists without Alembic tracking, stamp it once.
set +e
python3 - <<'PY'
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
    python3 -m flask --app dashboard.app:app db stamp "$BASELINE_REVISION"
elif [[ $status -ne 0 ]]; then
    echo "Failed to inspect schema state before migration."
    exit $status
fi

set +e
upgrade_output=$(python3 -m flask --app dashboard.app:app db upgrade 2>&1)
upgrade_status=$?
set -e

if [[ $upgrade_status -ne 0 ]]; then
    echo "$upgrade_output"
    if echo "$upgrade_output" | grep -qi "Can't locate revision identified by"; then
        echo "Unknown Alembic revision found; stamping current head and retrying upgrade."
        python3 -m flask --app dashboard.app:app db stamp head
        python3 -m flask --app dashboard.app:app db upgrade
    else
        echo "Marketing database migration failed."
        exit $upgrade_status
    fi
else
    echo "$upgrade_output"
fi

# Lead Radar and other runtime tables are defined in SQLAlchemy models but are
# not yet fully represented in Alembic revisions. Ensure they exist.
python3 - <<'PY'
from dashboard.app import app
from dashboard.models import db
from dashboard import lead_radar_models  # noqa: F401
from dashboard import marketing_calendar_models  # noqa: F401

with app.app_context():
    db.create_all()
    print("Ensured runtime SQLAlchemy tables exist (including Lead Radar).")
PY

python3 "$PROJECT_ROOT/ops/verify_marketing_schema.py"

echo "Marketing database migrations complete."
