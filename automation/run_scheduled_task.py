#!/usr/bin/env python3
"""Execute a dashboard scheduled task by ID."""

import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

DB_PATH = project_root / 'data' / 'marketing_dashboard.db'


def _python_exec() -> str:
    venv_python = project_root / '.venv' / 'bin' / 'python'
    if venv_python.exists():
        return str(venv_python)
    return sys.executable or 'python3'


def _load_task(task_id: int) -> Dict[str, object]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT st.*, b.name AS brand_name
            FROM scheduled_tasks st
            LEFT JOIN brands b ON st.brand_id = b.id
            WHERE st.id = ?
            """,
            (task_id,),
        ).fetchone()
        if not row:
            raise ValueError(f'Scheduled task {task_id} not found')
        task = dict(row)
        try:
            task['parameters'] = json.loads(task.get('parameters') or '{}')
        except json.JSONDecodeError:
            task['parameters'] = {}
        return task
    finally:
        conn.close()


def _build_command(task: Dict[str, object]) -> List[str]:
    python_bin = _python_exec()
    brand_name = task.get('brand_name')
    params = task.get('parameters') or {}
    task_type = task.get('task_type')

    if task_type == 'discovery':
        command = [python_bin, str(project_root / 'automation' / 'run_influencer_discovery.py')]
        if brand_name:
            command.extend(['--brand', brand_name])
        else:
            command.append('--all-brands')
        command.extend(['--max-per-platform', str(params.get('max_per_platform', 10))])
        return command

    if task_type == 'enrichment':
        command = [python_bin, str(project_root / 'automation' / 'influencer_enrichment.py')]
        if brand_name:
            command.extend(['--brand', brand_name])
        else:
            command.append('--all')
        command.extend(['--max', str(params.get('max', 50))])
        return command

    if task_type == 'press':
        if not brand_name:
            raise ValueError('Press discovery tasks require a specific brand')
        return [
            python_bin,
            str(project_root / 'automation' / 'press_contact_discovery.py'),
            '--brand',
            brand_name,
            '--scope',
            str(params.get('scope', 'all')),
            '--max',
            str(params.get('max', 12)),
        ]

    if task_type == 'analytics':
        return [python_bin, str(project_root / 'automation' / 'weekly_analytics_report.py')]

    if task_type == 'outreach':
        return [python_bin, str(project_root / 'automation' / 'run_unified_outreach.py')]

    if task_type == 'social':
        return [python_bin, str(project_root / 'automation' / 'social_publisher_cron.py')]

    if task_type == 'report':
        return [python_bin, str(project_root / 'automation' / 'weekly_analytics_report.py')]

    if task_type == 'lead_radar_research':
        command = [python_bin, str(project_root / 'automation' / 'run_lead_radar_research.py')]
        if brand_name and brand_name != 'all':
            command.extend(['--brand', brand_name])
        command.extend(['--limit', str(params.get('limit', 25))])
        if params.get('source_id'):
            command.extend(['--source-id', str(params.get('source_id'))])
        return command

    if task_type == 'influencer_outreach_queue':
        command = [python_bin, str(project_root / 'automation' / 'process_influencer_outreach_queue.py')]
        if brand_name and brand_name != 'all':
            command.extend(['--brand', brand_name])
        command.extend(['--limit', str(params.get('limit', 100))])
        command.extend(['--status', str(params.get('status', 'queued'))])
        if params.get('platform'):
            command.extend(['--platform', str(params.get('platform'))])
        if bool(params.get('dry_run', False)):
            command.append('--dry-run')
        if bool(params.get('auto_mark_sent', False)):
            command.append('--auto-mark-sent')
        return command

    raise ValueError(f'Unsupported task type: {task_type}')


def _write_task_result(task_id: int, success: bool, output: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        now = datetime.utcnow().isoformat()
        if success:
            conn.execute(
                """
                UPDATE scheduled_tasks
                SET last_run_at = ?, run_count = COALESCE(run_count, 0) + 1,
                    last_result = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, output[-4000:], now, task_id),
            )
        else:
            conn.execute(
                """
                UPDATE scheduled_tasks
                SET last_run_at = ?, run_count = COALESCE(run_count, 0) + 1,
                    fail_count = COALESCE(fail_count, 0) + 1,
                    last_result = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, output[-4000:], now, task_id),
            )
        conn.commit()
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description='Run a dashboard scheduled task')
    parser.add_argument('--task-id', type=int, required=True)
    args = parser.parse_args()

    task = _load_task(args.task_id)
    command = _build_command(task)
    result = subprocess.run(command, capture_output=True, text=True, cwd=str(project_root), timeout=3600)
    output = (result.stdout or '') + (result.stderr or '')
    _write_task_result(args.task_id, result.returncode == 0, output)
    if output:
        print(output)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())