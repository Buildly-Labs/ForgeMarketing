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

# Migrations that must run for REAL (actual DDL) on their first application,
# because as of 2026-07-23 we confirmed (via direct production DB inspection)
# that their schema had never actually been applied there, even though earlier
# migrations up through 0019 had. This caused OperationalError: Unknown column
# crashes in production (Episode.active_segment_id, Show.second_screen_background,
# etc.) because the model code moved past 0019 but the migration that catches
# the DB up was never committed/run.
#
# The preflight below unconditionally wipes and fake-applies ALL production_ledger
# migration records on every deploy (that's how this script has always avoided
# re-running already-applied DDL). So we detect whether each of these migrations'
# actual schema is present BEFORE the wipe runs, and if not, apply it for real
# right after the fake-all step (which will have marked it fake-applied; we
# re-run it for real in that case, which is safe because CreateModel/AddField
# are the only op types used here and Django allows re-running a migration that
# was only fake-applied).
REAL_MIGRATIONS_TO_CATCH_UP=(
    "0020_segmenttemplate_sponsor_and_more"
    "0021_orgapikey_production__organiz_6459bb_idx_and_more"
)

# Preflight: does the schema for the catch-up migrations above already exist?
# Checked via a real, load-bearing column/table (not just django_migrations
# bookkeeping, which the wipe below destroys every deploy) so this is accurate
# regardless of what a previous partial deploy left in django_migrations.
NEEDS_CATCH_UP=$("$PYTHON_BIN" - <<'PY'
import os

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.getenv("DJANGO_SETTINGS_MODULE", "logic_service.settings.docker"),
)

try:
    import django
except Exception:
    print("no")
    raise SystemExit(0)

django.setup()

from django.db import connection

try:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() "
            "AND table_name = 'production_ledger_episode' "
            "AND column_name = 'active_segment_id'"
        )
        (has_column,) = cursor.fetchone()
        print("no" if has_column else "yes")
except Exception:
    # Can't introspect (e.g. sqlite/fresh DB) — let the normal fake-all path
    # below handle it; catch-up isn't meaningful on a brand-new database.
    print("no")
PY
)

# Preflight reset: wipe all production_ledger migration records, then
# fake-apply every migration so `migrate` never tries to re-run DDL that
# already exists in the DB. Any genuinely new migration (added after the
# schema was last deployed) will be faked along with the rest; to run a
# new migration for real, add it to REAL_MIGRATIONS_TO_CATCH_UP above.
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
        # Check if migrations table exists; if not, skip preflight (migrations table will be created by migrate)
        try:
            cursor.execute("SELECT COUNT(*) FROM django_migrations WHERE app = %s", [APP])
            count_before = cursor.fetchone()[0]
            cursor.execute("DELETE FROM django_migrations WHERE app = %s", [APP])
            print(f"Preflight: cleared {count_before} existing {APP} migration records; will fake-apply all.")
        except Exception as table_exc:
            # Table doesn't exist yet; normal for fresh DB. Let migrate create it.
            if "no such table" in str(table_exc).lower() or "doesn't exist" in str(table_exc).lower():
                print(f"Preflight: django_migrations table doesn't exist yet; will let migrate create it")
            else:
                raise
except Exception as exc:
    print(f"Migration preflight failed: {exc}")
    raise SystemExit(1)
PY

echo "Fake-applying all production_ledger migrations (schema already exists in DB)..."
"$PYTHON_BIN" manage.py migrate production_ledger --fake --no-input

if [[ "$NEEDS_CATCH_UP" == "yes" ]]; then
    echo "Schema catch-up needed: un-faking and re-applying the following migrations for real..."
    CATCH_UP_NAMES="$(IFS=,; echo "${REAL_MIGRATIONS_TO_CATCH_UP[*]}")" "$PYTHON_BIN" - <<'PY'
import os

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.getenv("DJANGO_SETTINGS_MODULE", "logic_service.settings.docker"),
)
import django
django.setup()
from django.db import connection

names = os.environ["CATCH_UP_NAMES"].split(",")
with connection.cursor() as cursor:
    for name in names:
        cursor.execute(
            "DELETE FROM django_migrations WHERE app = %s AND name = %s",
            ["production_ledger", name],
        )
        print(f"Un-faked production_ledger.{name}")
PY
    for migration in "${REAL_MIGRATIONS_TO_CATCH_UP[@]}"; do
        echo "Applying production_ledger.$migration for real..."
        "$PYTHON_BIN" manage.py migrate production_ledger "$migration" --no-input
    done
fi

echo "Applying Django core migrations (contenttypes/auth/admin/sessions)..."
"$PYTHON_BIN" manage.py migrate contenttypes --no-input
"$PYTHON_BIN" manage.py migrate auth --no-input
"$PYTHON_BIN" manage.py migrate admin --no-input
"$PYTHON_BIN" manage.py migrate sessions --no-input

# Apply authtoken and logic app migrations (run normally; schema is clean for these).
"$PYTHON_BIN" manage.py migrate authtoken --no-input
"$PYTHON_BIN" manage.py migrate logic --no-input

echo "Producer database migrations complete."
