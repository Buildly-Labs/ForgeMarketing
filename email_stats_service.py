#!/usr/bin/env python3
"""Runtime email statistics service for dashboard widgets."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict


project_root = Path(__file__).resolve().parent


class EmailStatsService:
    """Provide lightweight cron-job email statistics without test-only imports."""

    def get_cron_job_stats(self, job_id: str, days_back: int = 7) -> Dict[str, Any]:
        del days_back

        task = self._find_scheduled_task(job_id)
        if not task:
            return {'sent': 0, 'opens': 0, 'clicks': 0}

        last_result = self._parse_last_result(task.get('last_result'))
        return {
            'sent': self._coerce_metric(last_result, ['sent', 'emails_sent', 'total_sent', 'processed', 'count']),
            'opens': self._coerce_metric(last_result, ['opens', 'opened', 'open_count', 'total_opens']),
            'clicks': self._coerce_metric(last_result, ['clicks', 'clicked', 'click_count', 'total_clicks']),
        }

    def update_all_job_stats(self) -> Dict[str, Dict[str, Any]]:
        stats: Dict[str, Dict[str, Any]] = {}
        for task in self._get_scheduled_tasks():
            task_id = str(task['id'])
            stats[task_id] = self.get_cron_job_stats(task_id)

            normalized_type = self._normalize_key(task.get('task_type') or '')
            if normalized_type:
                stats.setdefault(normalized_type, stats[task_id])

            normalized_name = self._normalize_key(task.get('name') or '')
            if normalized_name:
                stats.setdefault(normalized_name, stats[task_id])

        return stats

    def _db_path(self) -> Path:
        return project_root / 'data' / 'marketing_dashboard.db'

    def _get_scheduled_tasks(self):
        db_path = self._db_path()
        if not db_path.exists():
            return []

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(
                """
                SELECT id, name, task_type, last_result
                FROM scheduled_tasks
                WHERE is_enabled = 1 OR is_enabled IS NULL
                ORDER BY id
                """
            ).fetchall()
        finally:
            conn.close()

    def _find_scheduled_task(self, job_id: str):
        normalized_job_id = self._normalize_key(job_id)
        for task in self._get_scheduled_tasks():
            task_id = str(task['id'])
            candidates = {
                task_id,
                self._normalize_key(task.get('task_type') or ''),
                self._normalize_key(task.get('name') or ''),
                self._normalize_key(f"scheduled_task_{task_id}"),
            }
            if job_id == task_id or normalized_job_id in candidates:
                return dict(task)
        return None

    def _normalize_key(self, value: str) -> str:
        return re.sub(r'[^a-z0-9]+', '_', (value or '').strip().lower()).strip('_')

    def _parse_last_result(self, raw_value: Any) -> Dict[str, Any]:
        if isinstance(raw_value, dict):
            return raw_value
        if not raw_value:
            return {}
        try:
            parsed = json.loads(raw_value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, json.JSONDecodeError):
            return {}

    def _coerce_metric(self, payload: Dict[str, Any], keys) -> int:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                return int(value)
            if isinstance(value, str) and value.strip().isdigit():
                return int(value.strip())
        return 0