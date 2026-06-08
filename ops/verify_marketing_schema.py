#!/usr/bin/env python3
"""Fail-fast schema verification for marketing auth-critical tables."""

import sys
from pathlib import Path

from sqlalchemy import inspect


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.app import app
from dashboard.models import db


REQUIRED_COLUMNS = {
    "users": {
        "id",
        "email",
        "password_hash",
        "display_name",
        "is_admin",
        "is_active_user",
        "must_change_password",
        "region",
        "created_at",
        "updated_at",
        "last_login_at",
    },
    "lead_sources": {
        "id",
        "brand_name",
        "name",
        "source_type",
        "query_keywords",
        "run_frequency",
        "is_active",
        "last_run_at",
        "next_run_at",
        "created_at",
        "updated_at",
    },
    "lead_candidates": {
        "id",
        "brand_name",
        "lead_source_id",
        "status",
        "created_at",
        "updated_at",
    },
    "research_jobs": {
        "id",
        "lead_source_id",
        "status",
        "results_count",
        "candidates_created",
        "created_at",
        "updated_at",
    },
}


if __name__ == "__main__":
    with app.app_context():
        inspector = inspect(db.engine)
        existing_tables = set(inspector.get_table_names())

        problems = []
        for table_name, required_cols in REQUIRED_COLUMNS.items():
            if table_name not in existing_tables:
                problems.append(f"Missing required table: {table_name}")
                continue

            existing_cols = {col["name"] for col in inspector.get_columns(table_name)}
            missing_cols = sorted(required_cols - existing_cols)
            if missing_cols:
                problems.append(
                    f"Missing required columns on {table_name}: {', '.join(missing_cols)}"
                )

        if problems:
            print("Marketing schema verification failed:")
            for issue in problems:
                print(f" - {issue}")
            raise SystemExit(1)

        print("Marketing schema verification passed.")
