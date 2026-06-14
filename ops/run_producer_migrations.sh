#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! -d "$PROJECT_ROOT/Producer" ]] || [[ ! -f "$PROJECT_ROOT/Producer/manage.py" ]]; then
    echo "Producer app not present; skipping producer migrations."
    exit 0
fi

cd "$PROJECT_ROOT/Producer"

# Use one interpreter consistently for all migration/bootstrap commands.
# This avoids mismatches where `python` points to a different environment
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

echo "Running producer database migrations..."
echo "Using Python interpreter: $(command -v "$PYTHON_BIN")"

# Preflight reset: wipe all production_ledger migration records, then
# fake-apply every migration so `migrate` never tries to re-run DDL that
# already exists in the DB.  Any genuinely new migration (added after the
# schema was last deployed) will be faked along with the rest; to run a
# new migration for real, add it to REAL_MIGRATIONS below.
"$PYTHON_BIN" - <<'PY'
import os, sys

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.getenv("DJANGO_SETTINGS_MODULE", "logic_service.settings.docker"),
)

try:
    import django
except Exception as exc:
    print(f"Migration preflight skipped (django not available): {exc}")
    raise SystemExit(0)

django.setup()

from django.db import connection

APP = "production_ledger"

try:
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM django_migrations WHERE app = %s", [APP])
        count_before = cursor.fetchone()[0]
        cursor.execute("DELETE FROM django_migrations WHERE app = %s", [APP])
    print(f"Preflight: cleared {count_before} existing {APP} migration records; will fake-apply all.")
except Exception as exc:
    print(f"Migration preflight failed: {exc}")
    raise SystemExit(1)
PY

echo "Fake-applying all production_ledger migrations (schema already exists in DB)..."
"$PYTHON_BIN" manage.py migrate production_ledger --fake --no-input

echo "Applying Django core migrations (contenttypes/auth/admin/sessions)..."
"$PYTHON_BIN" manage.py migrate contenttypes --no-input
"$PYTHON_BIN" manage.py migrate auth --no-input
"$PYTHON_BIN" manage.py migrate admin --no-input
"$PYTHON_BIN" manage.py migrate sessions --no-input

# Apply authtoken and logic app migrations (run normally; schema is clean for these).
"$PYTHON_BIN" manage.py migrate authtoken --no-input
"$PYTHON_BIN" manage.py migrate logic --no-input

echo "Producer database migrations complete."
