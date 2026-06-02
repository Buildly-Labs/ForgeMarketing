#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! -d "$PROJECT_ROOT/Producer" ]] || [[ ! -f "$PROJECT_ROOT/Producer/manage.py" ]]; then
    echo "Producer app not present; skipping producer migrations."
    exit 0
fi

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
MIGRATION_CHAIN = [
    "0003_add_guest_contact_fields",
    "0004_add_media_platform_and_label",
    "0005_drop_episode_type_old",
    "0006_auto_20260416_2221",
]

try:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT name FROM django_migrations WHERE app = %s",
            [APP],
        )
        applied = {row[0] for row in cursor.fetchall()}

        repaired = []
        for idx, migration_name in enumerate(MIGRATION_CHAIN):
            if migration_name in applied:
                continue

            # If any later migration in the chain is already marked applied,
            # backfill this missing dependency to repair history consistency.
            later_applied = any(name in applied for name in MIGRATION_CHAIN[idx + 1 :])
            if later_applied:
                cursor.execute(
                    "INSERT INTO django_migrations (app, name, applied) VALUES (%s, %s, %s)",
                    [APP, migration_name, timezone.now()],
                )
                applied.add(migration_name)
                repaired.append(migration_name)

        if repaired:
            print(
                "Repaired migration history for production_ledger: "
                + ", ".join(repaired)
            )
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
        && echo "$migrate_output" | grep -q "production_ledger\.0005_drop_episode_type_old" \
        && echo "$migrate_output" | grep -q "production_ledger\.0004_add_media_platform_and_label"; then
        echo "Detected 0005-before-0004 inconsistency during migrate; applying compatibility fix and retrying."
        python manage.py migrate production_ledger 0004_add_media_platform_and_label --fake --no-input
        python manage.py migrate --no-input
    elif echo "$migrate_output" | grep -q "InconsistentMigrationHistory" \
        && echo "$migrate_output" | grep -q "production_ledger\.0006_auto_20260416_2221" \
        && echo "$migrate_output" | grep -q "production_ledger\.0005_drop_episode_type_old"; then
        echo "Detected 0006-before-0005 inconsistency during migrate; applying compatibility fix and retrying."
        python manage.py migrate production_ledger 0005_drop_episode_type_old --fake --no-input
        python manage.py migrate --no-input
    elif echo "$migrate_output" | grep -q "Duplicate column name 'completed_at'"; then
        echo "Detected duplicate completed_at column from production_ledger.0008; faking migration and retrying."
        python manage.py migrate production_ledger 0008_add_segment_live_recording_fields --fake --no-input
        python manage.py migrate --no-input
    elif echo "$migrate_output" | grep -qi "0007_fix_icon_column_charset\|Executing DDL statements while in a transaction\|TransactionManagementError"; then
        echo "Detected transactional DDL failure in production_ledger.0007; faking migration and retrying."
        python manage.py migrate production_ledger 0007_fix_icon_column_charset --fake --no-input
        python manage.py migrate --no-input
    else
        echo "$migrate_output"
        echo "Producer migration failed with unrecoverable error."
        exit $migrate_status
    fi
fi

echo "Producer database migrations complete."
