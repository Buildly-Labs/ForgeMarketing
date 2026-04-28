#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT/Producer"

echo "Running producer database migrations..."

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
    echo "$migrate_output"
    if echo "$migrate_output" | grep -q "InconsistentMigrationHistory" \
        && echo "$migrate_output" | grep -q "production_ledger\.0006_auto_20260416_2221" \
        && echo "$migrate_output" | grep -q "production_ledger\.0005_drop_episode_type_old"; then
        echo "Detected 0006-before-0005 inconsistency; faking production_ledger 0005 and retrying."
        python manage.py migrate production_ledger 0005_drop_episode_type_old --fake --no-input
        python manage.py migrate --no-input
    else
        echo "Producer migration failed with unrecoverable error."
        exit $migrate_status
    fi
fi

echo "Producer database migrations complete."
