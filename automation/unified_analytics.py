#!/usr/bin/env python3
"""
Unified Outreach Analytics System
Works with the consolidated unified database for all brand analytics
"""

import sqlite3
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any
import json
import logging

class UnifiedAnalytics:
    """Analytics system for the consolidated unified outreach database"""
    
    def __init__(self, db_path: str = None):
        """Initialize with unified database path"""
        self.logger = logging.getLogger(__name__)
        # Use project root relative path or environment variable
        project_root = Path(__file__).parent.parent
        default_db = project_root / 'data' / 'unified_outreach.db'
        self.db_path = db_path or os.getenv('UNIFIED_DB_PATH', str(default_db))
    
    def get_all_brands_overview(self, days: int = 30) -> Dict[str, Any]:
        """Get comprehensive overview across all brands"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

            # Brand list comes from campaigns (targets table has no brand column)
            cursor.execute("SELECT COUNT(DISTINCT brand) FROM campaigns")
            total_brands = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM targets")
            total_targets = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM campaigns WHERE status = 'sent'")
            total_sent = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM campaigns WHERE replied = 1")
            total_responses = cursor.fetchone()[0]

            # Brand-specific metrics derived from campaigns
            cursor.execute("""
                SELECT
                    c.brand,
                    COUNT(DISTINCT c.target_id) as targets,
                    COUNT(DISTINCT c.id) as outreach_count,
                    COUNT(DISTINCT CASE WHEN c.status = 'sent' THEN c.id END) as sent_count,
                    COUNT(DISTINCT CASE WHEN c.replied = 1 THEN c.id END) as response_count
                FROM campaigns c
                GROUP BY c.brand
            """)

            brand_data = {}
            for row in cursor.fetchall():
                brand, targets, outreach, sent, responses = row
                response_rate = round((responses / sent) * 100, 1) if sent > 0 else 0.0
                brand_data[brand] = {
                    'total_targets': targets,
                    'contacted_targets': targets,
                    'outreach_count': outreach,
                    'emails_sent': sent,
                    'responses_received': responses,
                    'response_rate': response_rate
                }

            # Recent activity
            cursor.execute("""
                SELECT
                    c.brand,
                    t.name,
                    c.subject,
                    c.status,
                    c.sent_date,
                    c.replied
                FROM campaigns c
                LEFT JOIN targets t ON c.target_id = t.id
                WHERE c.sent_date >= ?
                ORDER BY c.sent_date DESC
                LIMIT 20
            """, (start_date,))

            recent_activity = []
            for row in cursor.fetchall():
                brand, target_name, subject, status, sent_date, replied = row
                recent_activity.append({
                    'brand': brand,
                    'target_name': target_name or 'Unknown',
                    'subject': subject or 'No subject',
                    'status': status,
                    'delivery_time': sent_date,
                    'type': 'response' if replied else 'outreach'
                })

            conn.close()

            overall_response_rate = round((total_responses / total_sent) * 100, 1) if total_sent > 0 else 0.0

            return {
                'period_days': days,
                'total_brands': total_brands,
                'overview': {
                    'total_targets': total_targets,
                    'total_emails_sent': total_sent,
                    'total_responses': total_responses,
                    'overall_response_rate': overall_response_rate
                },
                'brands': brand_data,
                'recent_activity': recent_activity,
                'daily_stats': [],
                'last_updated': datetime.now().isoformat()
            }

        except Exception as e:
            self.logger.error(f"Error getting all brands overview: {e}")
            return {'error': str(e)}
    
    def get_brand_performance(self, brand: str, days: int = 30) -> Dict[str, Any]:
        """Get detailed performance for a specific brand"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

            # Brand metrics derived from campaigns (targets has no brand column)
            cursor.execute("""
                SELECT
                    COUNT(DISTINCT c.target_id) as total_targets,
                    COUNT(DISTINCT CASE WHEN c.status = 'sent' THEN c.target_id END) as contacted_targets,
                    COUNT(DISTINCT c.id) as total_outreach,
                    COUNT(DISTINCT CASE WHEN c.status = 'sent' THEN c.id END) as sent_emails,
                    COUNT(DISTINCT CASE WHEN c.replied = 1 THEN c.id END) as total_responses
                FROM campaigns c
                WHERE c.brand = ?
            """, (brand,))

            metrics = cursor.fetchone()
            total_targets, contacted_targets, total_outreach, sent_emails, total_responses = metrics

            response_rate = round((total_responses / sent_emails) * 100, 1) if sent_emails > 0 else 0.0

            # Target details via campaigns JOIN targets
            cursor.execute("""
                SELECT
                    t.id,
                    t.name,
                    t.email,
                    t.category,
                    t.priority,
                    t.last_contacted,
                    t.contact_count,
                    COUNT(c.id) as outreach_count,
                    MAX(c.sent_date) as last_outreach,
                    COUNT(CASE WHEN c.replied = 1 THEN 1 END) as response_count
                FROM campaigns c
                JOIN targets t ON c.target_id = t.id
                WHERE c.brand = ? AND c.sent_date >= ?
                GROUP BY t.id
                ORDER BY t.last_contacted DESC, t.priority DESC
                LIMIT 50
            """, (brand, start_date))

            targets = []
            for row in cursor.fetchall():
                t_id, name, email, category, priority, last_contacted, contact_count, outreach_count, last_outreach, response_count = row
                targets.append({
                    'id': t_id,
                    'target_key': str(t_id),
                    'name': name,
                    'company_name': name,
                    'email': email,
                    'category': category,
                    'priority': priority,
                    'last_contacted': last_contacted,
                    'contact_count': contact_count,
                    'outreach_count': outreach_count,
                    'last_outreach': last_outreach,
                    'response_count': response_count,
                    'has_responded': response_count > 0
                })

            # Outreach history
            cursor.execute("""
                SELECT
                    c.id,
                    c.target_id,
                    t.name,
                    t.email,
                    c.subject,
                    c.status,
                    c.replied,
                    c.sent_date
                FROM campaigns c
                LEFT JOIN targets t ON c.target_id = t.id
                WHERE c.brand = ? AND c.sent_date >= ?
                ORDER BY c.sent_date DESC
                LIMIT 50
            """, (brand, start_date))

            outreach_history = []
            for row in cursor.fetchall():
                c_id, target_id, target_name, email, subject, status, replied, sent_date = row
                outreach_history.append({
                    'id': c_id,
                    'target_id': target_id,
                    'target_name': target_name,
                    'email_address': email,
                    'subject': subject,
                    'status': status,
                    'response_received': bool(replied),
                    'delivery_time': sent_date,
                    'response_status': 'replied' if replied else None,
                    'response_type': None
                })

            conn.close()

            return {
                'brand': brand,
                'period_days': days,
                'metrics': {
                    'total_targets': total_targets,
                    'contacted_targets': contacted_targets,
                    'total_outreach': total_outreach,
                    'emails_sent': sent_emails,
                    'responses_received': total_responses,
                    'response_rate': response_rate
                },
                'targets': targets,
                'outreach_history': outreach_history,
                'campaign_metrics': [],
                'last_updated': datetime.now().isoformat()
            }

        except Exception as e:
            self.logger.error(f"Error getting brand performance for {brand}: {e}")
            return {'error': str(e)}
    
    def get_cron_status_from_unified_db(self) -> List[Dict[str, Any]]:
        """Get cron job status inferred from unified database activity"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Active brands from campaigns and discovery_sessions
            cursor.execute("""
                SELECT DISTINCT brand FROM campaigns
                UNION
                SELECT DISTINCT brand FROM discovery_sessions
            """)
            active_brands = [row[0] for row in cursor.fetchall()]

            cron_jobs = []

            for brand in active_brands:
                # Recent outreach activity
                cursor.execute("""
                    SELECT MAX(sent_date) as last_outreach, COUNT(*) as total_outreach
                    FROM campaigns
                    WHERE brand = ? AND sent_date >= date('now', '-7 days')
                """, (brand,))
                outreach_data = cursor.fetchone()
                if outreach_data and outreach_data[1] > 0:
                    cron_jobs.append({
                        'name': f'{brand.title()} Outreach Campaign',
                        'type': 'outreach',
                        'brand': brand,
                        'schedule': '0 10 * * 1-5',
                        'status': 'active',
                        'last_run': outreach_data[0] or 'Unknown',
                        'next_run': self._calculate_next_weekday_run(),
                        'records_this_week': outreach_data[1]
                    })

                # Recent discovery activity
                cursor.execute("""
                    SELECT MAX(session_date) as last_discovery, COUNT(*) as total_sessions
                    FROM discovery_sessions
                    WHERE brand = ? AND session_date >= date('now', '-7 days')
                """, (brand,))
                discovery_data = cursor.fetchone()
                if discovery_data and discovery_data[1] > 0:
                    cron_jobs.append({
                        'name': f'{brand.title()} Target Discovery',
                        'type': 'discovery',
                        'brand': brand,
                        'schedule': '0 9 * * *',
                        'status': 'active',
                        'last_run': discovery_data[0] or 'Unknown',
                        'next_run': 'Tomorrow 9:00 AM',
                        'sessions_this_week': discovery_data[1]
                    })

            conn.close()
            return cron_jobs

        except Exception as e:
            self.logger.error(f"Error getting cron status from unified DB: {e}")
            return []
    
    def _calculate_next_weekday_run(self) -> str:
        """Calculate next weekday 10 AM run"""
        now = datetime.now()
        next_run = now.replace(hour=10, minute=0, second=0, microsecond=0)
        
        # If it's past 10 AM today, move to next day
        if now.hour >= 10:
            next_run += timedelta(days=1)
        
        # Skip weekends
        while next_run.weekday() >= 5:  # 5=Saturday, 6=Sunday
            next_run += timedelta(days=1)
        
        return next_run.strftime('%Y-%m-%d 10:00 AM')
    
    def get_database_summary(self) -> Dict[str, Any]:
        """Get summary of unified database contents"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Only query tables that actually exist
            tables = ['targets', 'campaigns', 'discovery_sessions']

            table_counts = {}
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                table_counts[table] = cursor.fetchone()[0]

            cursor.execute("SELECT brand, COUNT(*) as count FROM campaigns GROUP BY brand ORDER BY count DESC")
            brand_outreach = dict(cursor.fetchall())

            cursor.execute("SELECT brand, COUNT(*) as count FROM discovery_sessions GROUP BY brand ORDER BY count DESC")
            brand_discovery = dict(cursor.fetchall())

            conn.close()

            return {
                'database_path': self.db_path,
                'table_counts': table_counts,
                'total_records': sum(table_counts.values()),
                'brand_targets': brand_outreach,
                'brand_outreach': brand_outreach,
                'brand_discovery': brand_discovery,
                'last_checked': datetime.now().isoformat()
            }

        except Exception as e:
            return {'error': str(e)}
    
    def get_recent_outreach_activity(self, limit: int = 50, brand: str = None) -> List[Dict[str, Any]]:
        """Get recent outreach activity with optional brand filter"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            query = """
                SELECT
                    c.id,
                    c.brand,
                    c.target_id,
                    t.name,
                    t.email,
                    c.subject,
                    c.message,
                    c.sent_date,
                    c.status,
                    c.replied
                FROM campaigns c
                LEFT JOIN targets t ON c.target_id = t.id
            """

            params = []
            if brand:
                query += " WHERE c.brand = ?"
                params.append(brand)
            query += " ORDER BY c.sent_date DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            columns = ['id', 'brand', 'target_id', 'target_name', 'target_email',
                       'subject', 'email_content', 'delivery_time', 'status', 'response_received']

            activities = []
            for row in rows:
                activity = dict(zip(columns, row))
                activity['campaign_id'] = activity['id']
                activity['parsed_content'] = None
                activities.append(activity)

            conn.close()
            return activities

        except Exception as e:
            self.logger.error(f"Error getting recent outreach activity: {e}")
            return []

def main():
    """Test the unified analytics system"""
    print("=== Unified Outreach Analytics Test ===")
    
    analytics = UnifiedAnalytics()

    # Database summary
    print("\n=== Database Summary ===")
    summary = analytics.get_database_summary()
    if 'error' not in summary:
        print(f"Database: {summary['database_path']}")
        print(f"Total Records: {summary['total_records']}")
        for table, count in summary['table_counts'].items():
            print(f"  {table}: {count}")
        
        print("Brand Targets:")
        for brand, count in summary['brand_targets'].items():
            print(f"  {brand}: {count}")
    
    # All brands overview
    print("\n=== All Brands Overview ===")
    overview = analytics.get_all_brands_overview(30)
    if 'error' not in overview:
        print(f"Total Brands: {overview['total_brands']}")
        print(f"Overall Stats: {overview['overview']}")
        
        for brand, data in overview['brands'].items():
            print(f"{brand}: {data['emails_sent']} sent, {data['responses_received']} responses ({data['response_rate']}%)")
    
    # Cron status
    print("\n=== Inferred Cron Jobs ===")
    crons = analytics.get_cron_status_from_unified_db()
    for cron in crons:
        print(f"{cron['name']}: {cron['status']} (last: {cron['last_run']})")

# Backwards-compatibility alias — app.py imports this name
UnifiedOutreachAnalytics = UnifiedAnalytics

if __name__ == "__main__":
    main()