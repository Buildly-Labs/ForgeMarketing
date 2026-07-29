#!/usr/bin/env python3
"""Unified outreach data helpers for content/data-driven flows."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / 'data' / 'unified_outreach.db'


def open_conn(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def get_approved_targets(conn: sqlite3.Connection, brand: str) -> List[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM unified_targets WHERE brand = ? AND target_key IS NOT NULL ORDER BY priority DESC, created_at ASC",
        (brand,)
    ).fetchall()


def get_recent_campaigns(conn: sqlite3.Connection, brand: str, limit: int = 25) -> List[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM unified_outreach_log WHERE brand = ? ORDER BY created_at DESC LIMIT ?",
        (brand, limit)
    ).fetchall()


def build_content_summary(brand: str, db_path: Optional[str] = None) -> Dict[str, Any]:
    conn = open_conn(db_path)
    try:
        targets = [dict(row) for row in get_approved_targets(conn, brand)]
        outreach = [dict(row) for row in get_recent_campaigns(conn, brand, limit=50)]
        return {
            'brand': brand,
            'generated_at': datetime.now().isoformat(),
            'target_count': len(targets),
            'outreach_count': len(outreach),
            'data_source': 'live_db',
            'targets': targets,
            'recent_outreach': outreach[:10],
        }
    finally:
        conn.close()
