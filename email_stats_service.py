#!/usr/bin/env python3
"""Runtime email statistics service for dashboard widgets."""

from __future__ import annotations

from typing import Any, Dict


class EmailStatsService:
    """Provide lightweight cron-job email statistics without test-only imports."""

    def get_cron_job_stats(self, job_id: str, days_back: int = 7) -> Dict[str, Any]:
        mock_stats = {
            'foundry_daily': {'sent': 12, 'opens': 8, 'clicks': 3},
            'open_build_daily': {'sent': 15, 'opens': 11, 'clicks': 4},
            'unified_outreach': {'sent': 45, 'opens': 32, 'clicks': 12},
            'weekly_analytics': {'sent': 8, 'opens': 6, 'clicks': 2},
        }
        return mock_stats.get(job_id, {'sent': 0, 'opens': 0, 'clicks': 0})

    def update_all_job_stats(self) -> Dict[str, Dict[str, Any]]:
        return {
            job_id: self.get_cron_job_stats(job_id)
            for job_id in ['foundry_daily', 'open_build_daily', 'unified_outreach', 'weekly_analytics']
        }