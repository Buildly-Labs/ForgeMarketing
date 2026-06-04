#!/usr/bin/env python3
"""Run due Lead Radar research jobs from configured lead sources."""

import argparse
import json
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dashboard.app import app
from dashboard.lead_radar_service import run_due_source_research_jobs


def main() -> int:
    parser = argparse.ArgumentParser(description="Run due Lead Radar research jobs")
    parser.add_argument("--brand", default="", help="Optional brand name filter")
    parser.add_argument("--source-id", type=int, default=0, help="Optional single source id")
    parser.add_argument("--limit", type=int, default=25, help="Max sources to process")
    args = parser.parse_args()

    with app.app_context():
        summary = run_due_source_research_jobs(
            brand_name=(args.brand or None),
            source_id=(args.source_id or None),
            limit=args.limit,
        )

    print(json.dumps({
        "success": True,
        "run_at": summary["run_at"],
        "sources_considered": summary["sources_considered"],
        "jobs_completed": summary["jobs_completed"],
        "jobs_failed": summary["jobs_failed"],
        "total_items_processed": summary["total_items_processed"],
        "total_candidates_created": summary["total_candidates_created"],
    }))

    return 0 if summary["jobs_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
