#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT/Producer"

# Ensure deployment runs against the correct settings without manual exports.
if [[ -z "${RUNNING_IN_DOCKER:-}" ]]; then
    if [[ -f "/.dockerenv" ]]; then
        export RUNNING_IN_DOCKER="1"
    else
        export RUNNING_IN_DOCKER="0"
    fi
fi

if [[ -z "${DJANGO_SETTINGS_MODULE:-}" ]]; then
    if [[ "${RUNNING_IN_DOCKER}" == "1" ]]; then
        export DJANGO_SETTINGS_MODULE="logic_service.settings.docker"
    else
        export DJANGO_SETTINGS_MODULE="logic_service.settings.dev"
    fi
fi

echo "Producer migration env: DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE}, RUNNING_IN_DOCKER=${RUNNING_IN_DOCKER}"

if command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
else
    echo "Python executable not found (expected python or python3)."
    exit 1
fi

echo "Running producer database migrations..."

# Preflight repair for known production_ledger migration ordering issue:
# 0006 recorded as applied while dependency 0005 is missing.
"${PYTHON_BIN}" - <<'PY'
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

# Historical compatibility fakes.
# IMPORTANT: Only fake when the actual DB tables already exist (i.e. upgrading an
# existing deployment, not a fresh install). On a fresh DB, faking 0002 marks 0001
# as applied without creating any tables, causing every subsequent migration to fail
# with "table doesn't exist".
set +e
has_tables=$("${PYTHON_BIN}" - <<'PYCHECK' 2>/dev/null
import os, sys
os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.getenv("DJANGO_SETTINGS_MODULE", "logic_service.settings.docker"),
)
try:
    import django; django.setup()
    from django.db import connection
    tables = connection.introspection.table_names()
    print("yes" if "production_ledger_episode" in tables else "no")
except Exception:
    print("no")
PYCHECK
)
if [[ "$has_tables" == "yes" ]]; then
    echo "Existing schema detected — applying historical compatibility fakes."
    "${PYTHON_BIN}" manage.py migrate production_ledger 0002 --fake --no-input >/tmp/producer_mig_pre_1.log 2>&1
    "${PYTHON_BIN}" manage.py migrate logic 0002 --fake --no-input >/tmp/producer_mig_pre_2.log 2>&1
else
    echo "Fresh database detected — skipping historical fakes (tables will be created normally)."
fi
set -e

max_attempts=6
attempt=1

while [[ $attempt -le $max_attempts ]]; do
    set +e
    migrate_output=$("${PYTHON_BIN}" manage.py migrate --no-input 2>&1)
    migrate_status=$?
    set -e

    if [[ $migrate_status -eq 0 ]]; then
        break
    fi

    failed_production_ledger_migration=$(
        echo "$migrate_output" \
            | sed -n "s/.*Applying production_ledger\.\([a-zA-Z0-9_]*\).*/\1/p" \
            | tail -1
    )

    if echo "$migrate_output" | grep -q "InconsistentMigrationHistory" \
        && echo "$migrate_output" | grep -q "production_ledger\.0005_drop_episode_type_old" \
        && echo "$migrate_output" | grep -q "production_ledger\.0004_add_media_platform_and_label"; then
        echo "Detected 0005-before-0004 inconsistency during migrate; applying compatibility fix (attempt ${attempt}/${max_attempts})."
        "${PYTHON_BIN}" manage.py migrate production_ledger 0004_add_media_platform_and_label --fake --no-input
    elif echo "$migrate_output" | grep -q "InconsistentMigrationHistory" \
        && echo "$migrate_output" | grep -q "production_ledger\.0006_auto_20260416_2221" \
        && echo "$migrate_output" | grep -q "production_ledger\.0005_drop_episode_type_old"; then
        echo "Detected 0006-before-0005 inconsistency during migrate; applying compatibility fix (attempt ${attempt}/${max_attempts})."
        "${PYTHON_BIN}" manage.py migrate production_ledger 0005_drop_episode_type_old --fake --no-input
    elif echo "$migrate_output" | grep -q "Duplicate column name 'completed_at'"; then
        echo "Detected duplicate completed_at column from production_ledger.0008; faking migration (attempt ${attempt}/${max_attempts})."
        "${PYTHON_BIN}" manage.py migrate production_ledger 0008_add_segment_live_recording_fields --fake --no-input
    elif echo "$migrate_output" | grep -q "production_ledger_showjoinrequest" \
        && echo "$migrate_output" | grep -q "already exists" \
        && echo "$migrate_output" | grep -q "production_ledger\.0009_show_join_request"; then
        echo "Detected existing production_ledger_showjoinrequest table; faking production_ledger.0009 (attempt ${attempt}/${max_attempts})."
        "${PYTHON_BIN}" manage.py migrate production_ledger 0009_show_join_request --fake --no-input
    elif echo "$migrate_output" | grep -q "production_ledger_backgroundtask" \
        && echo "$migrate_output" | grep -Eqi "already exists"; then
        echo "Detected existing production_ledger_backgroundtask table; faking production_ledger.0017 (attempt ${attempt}/${max_attempts})."
        "${PYTHON_BIN}" manage.py migrate production_ledger 0017_background_task --fake --no-input
    elif echo "$migrate_output" | grep -q "production_ledger_orgapikey" \
        && echo "$migrate_output" | grep -Eqi "already exists"; then
        echo "Detected existing production_ledger_orgapikey table; faking production_ledger.0016 (attempt ${attempt}/${max_attempts})."
        "${PYTHON_BIN}" manage.py migrate production_ledger 0016_orgapikey --fake --no-input
    elif echo "$migrate_output" | grep -q "0013_videoshort_platform_captions" \
        && echo "$migrate_output" | grep -Eqi "already exists|duplicate column|duplicate key"; then
        echo "Detected existing platform_captions column; faking production_ledger.0013 (attempt ${attempt}/${max_attempts})."
        "${PYTHON_BIN}" manage.py migrate production_ledger 0013_videoshort_platform_captions --fake --no-input
    elif echo "$migrate_output" | grep -q "production_ledger\.0010_distribution_transcription_shorts" \
        && echo "$migrate_output" | grep -qi "already exists" \
        && echo "$migrate_output" | grep -q "production_ledger_podcastdistribution\|production_ledger_podcastfeedconfig\|production_ledger_videoshort"; then
        echo "Detected existing 0010 distribution/shorts tables; faking production_ledger.0010 (attempt ${attempt}/${max_attempts})."
        "${PYTHON_BIN}" manage.py migrate production_ledger 0010_distribution_transcription_shorts --fake --no-input
    elif [[ -n "$failed_production_ledger_migration" ]] \
        && echo "$migrate_output" | grep -Eqi "already exists|duplicate column|duplicate key|duplicate index|index .* already exists|column .* already exists"; then
        echo "Detected schema drift while applying production_ledger.${failed_production_ledger_migration}; faking migration (attempt ${attempt}/${max_attempts})."
        "${PYTHON_BIN}" manage.py migrate production_ledger "${failed_production_ledger_migration}" --fake --no-input
    elif echo "$migrate_output" | grep -qi "0007_fix_icon_column_charset\|CHARACTER SET\|MODIFY COLUMN"; then
        echo "Detected failure in production_ledger.0007 charset migration; faking migration (attempt ${attempt}/${max_attempts})."
        "${PYTHON_BIN}" manage.py migrate production_ledger 0007_fix_icon_column_charset --fake --no-input
    else
        echo "$migrate_output"
        echo "Producer migration failed with unrecoverable error."
        touch /tmp/forge_migrations_failed
        exit $migrate_status
    fi

    attempt=$((attempt + 1))
done

if [[ ${migrate_status:-1} -ne 0 ]]; then
    echo "$migrate_output"
    echo "Producer migration failed after ${max_attempts} recovery attempts."
    touch /tmp/forge_migrations_failed
    exit ${migrate_status:-1}
fi

echo "Producer database migrations complete."

echo "Running Producer post-migration checks..."
"${PYTHON_BIN}" manage.py showmigrations production_ledger --list
"${PYTHON_BIN}" manage.py check
echo "Producer post-migration checks complete."
