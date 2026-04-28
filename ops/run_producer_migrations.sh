#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT/Producer"

echo "Running producer database migrations..."

# Preflight repair for known production_ledger migration ordering issue:
# 0006 recorded as applied while dependency 0005 is missing.
python - <<'PY'
import os
import sys

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.getenv("DJANGO_SETTINGS_MODULE", "logic_service.settings.docker"),
)

try:
    import django
except Exception as exc:
    print(f"Migration preflight check skipped (django not available): {exc}")
    raise SystemExit(0)

django.setup()

from django.db import connection
from django.utils import timezone

APP = "production_ledger"
MIG_0005 = "0005_drop_episode_type_old"
MIG_0006 = "0006_auto_20260416_2221"

try:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM django_migrations WHERE app = %s AND name = %s LIMIT 1",
            [APP, MIG_0006],
        )
        has_0006 = cursor.fetchone() is not None

        cursor.execute(
            "SELECT 1 FROM django_migrations WHERE app = %s AND name = %s LIMIT 1",
            [APP, MIG_0005],
        )
        has_0005 = cursor.fetchone() is not None

        if has_0006 and not has_0005:
            cursor.execute(
                "INSERT INTO django_migrations (app, name, applied) VALUES (%s, %s, %s)",
                [APP, MIG_0005, timezone.now()],
            )
            print("Repaired migration history: marked production_ledger.0005_drop_episode_type_old as applied.")
except Exception as exc:
    # Do not hard-fail preflight; migrate step below still handles recovery.
    print(f"Migration preflight check skipped: {exc}")
    raise SystemExit(0)
PY

# Historical compatibility fakes (safe to repeat; no-op when already applied).
set +e
python manage.py migrate production_ledger 0002 --fake --no-input >/tmp/producer_mig_pre_1.log 2>&1
python manage.py migrate logic 0002 --fake --no-input >/tmp/producer_mig_pre_2.log 2>&1
set -e

set +e
migrate_output=$(python manage.py migrate --no-input 2>&1)
migrate_status=$?
set -e

if [[ $migrate_status -ne 0 ]]; then
    if echo "$migrate_output" | grep -q "InconsistentMigrationHistory" \
        && echo "$migrate_output" | grep -q "production_ledger\.0006_auto_20260416_2221" \
        && echo "$migrate_output" | grep -q "production_ledger\.0005_drop_episode_type_old"; then
        echo "Detected 0006-before-0005 inconsistency during migrate; applying compatibility fix and retrying."
        python manage.py migrate production_ledger 0005_drop_episode_type_old --fake --no-input
        python manage.py migrate --no-input
    else
        echo "$migrate_output"
        echo "Producer migration failed with unrecoverable error."
        exit $migrate_status
    fi
fi

echo "Producer database migrations complete."
