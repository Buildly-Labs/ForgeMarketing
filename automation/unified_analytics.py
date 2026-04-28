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
            
            # Get date filter
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            
            # Overall metrics
            cursor.execute("SELECT COUNT(DISTINCT brand) FROM unified_targets")
            total_brands = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM unified_targets")
            total_targets = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM unified_outreach_log WHERE status = 'sent'")
            total_sent = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM unified_responses WHERE response_status != 'auto_reply'")
            total_responses = cursor.fetchone()[0]
            
            # Brand-specific metrics
            cursor.execute("""
                SELECT 
                    t.brand,
                    COUNT(DISTINCT t.id) as targets,
                    COUNT(DISTINCT CASE WHEN t.last_contacted IS NOT NULL THEN t.id END) as contacted,
                    COUNT(DISTINCT o.id) as outreach_count,
                    COUNT(DISTINCT CASE WHEN o.status = 'sent' THEN o.id END) as sent_count,
                    COUNT(DISTINCT r.id) as response_count
                FROM unified_targets t
                LEFT JOIN unified_outreach_log o ON t.id = o.target_id
                LEFT JOIN unified_responses r ON t.id = r.target_id
                GROUP BY t.brand
            """)
            
            brand_data = {}
            for row in cursor.fetchall():
                brand, targets, contacted, outreach, sent, responses = row
                
                response_rate = 0.0
                if sent > 0:
                    response_rate = round((responses / sent) * 100, 1)
                
                brand_data[brand] = {
                    'total_targets': targets,
                    'contacted_targets': contacted,
                    'outreach_count': outreach,
                    'emails_sent': sent,
                    'responses_received': responses,
                    'response_rate': response_rate
                }
            
            # Recent activity across all brands
            cursor.execute("""
                SELECT 
                    o.brand,
                    t.name as target_name,
                    o.subject,
                    o.status,
                    o.delivery_time,
                    o.response_received
                FROM unified_outreach_log o
                LEFT JOIN unified_targets t ON o.target_id = t.id
                WHERE o.delivery_time >= ?
                ORDER BY o.delivery_time DESC
                LIMIT 20
            """, (start_date,))
            
            recent_activity = []
            for row in cursor.fetchall():
                brand, target_name, subject, status, delivery_time, response_received = row
                recent_activity.append({
                    'brand': brand,
                    'target_name': target_name or 'Unknown',
                    'subject': subject or 'No subject',
                    'status': status,
                    'delivery_time': delivery_time,
                    'type': 'response' if response_received else 'outreach'
                })
            
            # Daily stats for the period
            cursor.execute("""
                SELECT 
                    date,
                    brand,
                    SUM(targets_added) as targets_added,
                    SUM(emails_sent) as emails_sent,
                    SUM(responses_received) as responses_received
                FROM unified_campaign_metrics
                WHERE date >= ? AND metric_type = 'daily_stats'
                GROUP BY date, brand
                ORDER BY date DESC
                LIMIT 14
            """, (start_date,))
            
            daily_stats = []
            for row in cursor.fetchall():
                date, brand, targets_added, emails_sent, responses_received = row
                daily_stats.append({
                    'date': date,
                    'brand': brand,
                    'targets_added': targets_added or 0,
                    'emails_sent': emails_sent or 0,
                    'responses_received': responses_received or 0
                })
            
            conn.close()
            
            # Calculate overall response rate
            overall_response_rate = 0.0
            if total_sent > 0:
                overall_response_rate = round((total_responses / total_sent) * 100, 1)
            
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
                'daily_stats': daily_stats,
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
            
            # Brand metrics
            cursor.execute("""
                SELECT 
                    COUNT(DISTINCT t.id) as total_targets,
                    COUNT(DISTINCT CASE WHEN t.last_contacted IS NOT NULL THEN t.id END) as contacted_targets,
                    COUNT(DISTINCT o.id) as total_outreach,
                    COUNT(DISTINCT CASE WHEN o.status = 'sent' THEN o.id END) as sent_emails,
                    COUNT(DISTINCT r.id) as total_responses
                FROM unified_targets t
                LEFT JOIN unified_outreach_log o ON t.id = o.target_id AND o.brand = ?
                LEFT JOIN unified_responses r ON t.id = r.target_id AND r.brand = ?
                WHERE t.brand = ?
            """, (brand, brand, brand))
            
            metrics = cursor.fetchone()
            total_targets, contacted_targets, total_outreach, sent_emails, total_responses = metrics
            
            # Calculate response rate
            response_rate = 0.0
            if sent_emails > 0:
                response_rate = round((total_responses / sent_emails) * 100, 1)
            
            # Target details
            cursor.execute("""
                SELECT 
                    t.id,
                    t.target_key,
                    t.name,
                    t.company_name,
                    t.email,
                    t.category,
                    t.priority,
                    t.last_contacted,
                    t.contact_count,
                    COUNT(o.id) as outreach_count,
                    MAX(o.delivery_time) as last_outreach,
                    COUNT(r.id) as response_count
                FROM unified_targets t
                LEFT JOIN unified_outreach_log o ON t.id = o.target_id
                LEFT JOIN unified_responses r ON t.id = r.target_id
                WHERE t.brand = ? AND (t.created_at >= ? OR t.last_contacted >= ?)
                GROUP BY t.id
                ORDER BY t.last_contacted DESC, t.priority DESC
                LIMIT 50
            """, (brand, start_date, start_date))
            
            targets = []
            for row in cursor.fetchall():
                target_data = {
                    'id': row[0],
                    'target_key': row[1],
                    'name': row[2],
                    'company_name': row[3] or row[2],
                    'email': row[4],
                    'category': row[5],
                    'priority': row[6],
                    'last_contacted': row[7],
                    'contact_count': row[8],
                    'outreach_count': row[9],
                    'last_outreach': row[10],
                    'response_count': row[11],
                    'has_responded': row[11] > 0
                }
                targets.append(target_data)
            
            # Outreach history
            cursor.execute("""
                SELECT 
                    o.id,
                    o.target_id,
                    t.name as target_name,
                    o.email_address,
                    o.subject,
                    o.status,
                    o.response_received,
                    o.delivery_time,
                    r.response_status,
                    r.response_type
                FROM unified_outreach_log o
                LEFT JOIN unified_targets t ON o.target_id = t.id
                LEFT JOIN unified_responses r ON o.id = r.outreach_log_id
                WHERE o.brand = ? AND o.delivery_time >= ?
                ORDER BY o.delivery_time DESC
                LIMIT 50
            """, (brand, start_date))
            
            outreach_history = []
            for row in cursor.fetchall():
                outreach_data = {
                    'id': row[0],
                    'target_id': row[1],
                    'target_name': row[2],
                    'email_address': row[3],
                    'subject': row[4],
                    'status': row[5],
                    'response_received': bool(row[6]),
                    'delivery_time': row[7],
                    'response_status': row[8],
                    'response_type': row[9]
                }
                outreach_history.append(outreach_data)
            
            # Campaign metrics over time
            cursor.execute("""
                SELECT 
                    date,
                    targets_added,
                    emails_sent,
                    responses_received,
                    website_visitors,
                    website_pageviews
                FROM unified_campaign_metrics
                WHERE brand = ? AND date >= ?
                ORDER BY date DESC
            """, (brand, start_date))
            
            campaign_metrics = []
            for row in cursor.fetchall():
                metrics_data = {
                    'date': row[0],
                    'targets_added': row[1] or 0,
                    'emails_sent': row[2] or 0,
                    'responses_received': row[3] or 0,
                    'website_visitors': row[4] or 0,
                    'website_pageviews': row[5] or 0
                }
                campaign_metrics.append(metrics_data)
            
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
                'campaign_metrics': campaign_metrics,
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
            
            # Get brands with recent activity
            cursor.execute("""
                SELECT DISTINCT brand FROM unified_targets 
                UNION 
                SELECT DISTINCT brand FROM unified_outreach_log 
                UNION 
                SELECT DISTINCT brand FROM unified_campaign_metrics
            """)
            
            active_brands = [row[0] for row in cursor.fetchall()]
            
            cron_jobs = []
            
            for brand in active_brands:
                # Check for recent outreach (indicates outreach cron is active)
                cursor.execute("""
                    SELECT MAX(delivery_time) as last_outreach, COUNT(*) as total_outreach
                    FROM unified_outreach_log 
                    WHERE brand = ? AND delivery_time >= date('now', '-7 days')
                """, (brand,))
                
                outreach_data = cursor.fetchone()
                if outreach_data and outreach_data[1] > 0:
                    cron_jobs.append({
                        'name': f'{brand.title()} Outreach Campaign',
                        'type': 'outreach',
                        'brand': brand,
                        'schedule': '0 10 * * 1-5',  # 10 AM weekdays
                        'status': 'active',
                        'last_run': outreach_data[0] or 'Unknown',
                        'next_run': self._calculate_next_weekday_run(),
                        'records_this_week': outreach_data[1]
                    })
                
                # Check for recent metrics (indicates analytics cron is active)
                cursor.execute("""
                    SELECT MAX(date) as last_metrics, COUNT(*) as total_metrics
                    FROM unified_campaign_metrics 
                    WHERE brand = ? AND date >= date('now', '-7 days')
                """, (brand,))
                
                metrics_data = cursor.fetchone()
                if metrics_data and metrics_data[1] > 0:
                    cron_jobs.append({
                        'name': f'{brand.title()} Analytics Report',
                        'type': 'analytics_email', 
                        'brand': brand,
                        'schedule': '0 8 * * *',  # 8 AM daily
                        'status': 'active',
                        'last_run': metrics_data[0] or 'Unknown',
                        'next_run': 'Tomorrow 8:00 AM',
                        'records_this_week': metrics_data[1]
                    })
                
                # Check for discovery activity
                cursor.execute("""
                    SELECT MAX(discovery_date) as last_discovery, COUNT(*) as total_sessions
                    FROM unified_discovery_sessions 
                    WHERE brand = ? AND discovery_date >= date('now', '-7 days')
                """, (brand,))
                
                discovery_data = cursor.fetchone()
                if discovery_data and discovery_data[1] > 0:
                    cron_jobs.append({
                        'name': f'{brand.title()} Target Discovery',
                        'type': 'discovery',
                        'brand': brand,
                        'schedule': '0 9 * * *',  # 9 AM daily
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
            
            # Table counts
            tables = ['unified_targets', 'unified_outreach_log', 'unified_discovery_sessions', 
                     'unified_campaign_metrics', 'unified_responses']
            
            table_counts = {}
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                table_counts[table] = cursor.fetchone()[0]
            
            # Brand breakdown
            cursor.execute("""
                SELECT brand, COUNT(*) as count
                FROM unified_targets 
                GROUP BY brand
                ORDER BY count DESC
            """)
            
            brand_targets = dict(cursor.fetchall())
            
            cursor.execute("""
                SELECT brand, COUNT(*) as count
                FROM unified_outreach_log 
                GROUP BY brand
                ORDER BY count DESC
            """)
            
            brand_outreach = dict(cursor.fetchall())
            
            conn.close()
            
            return {
                'database_path': self.db_path,
                'table_counts': table_counts,
                'total_records': sum(table_counts.values()),
                'brand_targets': brand_targets,
                'brand_outreach': brand_outreach,
                'last_checked': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {'error': str(e)}
    
    def get_recent_outreach_activity(self, limit: int = 50, brand: str = None) -> List[Dict[str, Any]]:
        """Get recent outreach activity with optional brand filter"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Base query for recent outreach activity
            query = """
                SELECT 
                    o.id,
                    o.brand,
                    o.target_id,
                    t.name as target_name,
                    t.email as target_email,
                    o.subject,
                    o.email_content,
                    o.delivery_time,
                    o.status,
                    o.response_received,
                    o.response_content,
                    o.campaign_id
                FROM unified_outreach_log o
                LEFT JOIN unified_targets t ON o.target_id = t.id AND o.brand = t.brand
            """
            
            params = []
            
            if brand:
                query += " WHERE o.brand = ?"
                params.append(brand)
            
            query += " ORDER BY o.delivery_time DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            # Convert to list of dictionaries
            columns = [desc[0] for desc in cursor.description]
            activities = []
            
            for row in rows:
                activity = dict(zip(columns, row))
                
                # Parse JSON content if exists
                if activity['email_content']:
                    try:
                        content = json.loads(activity['email_content'])
                        activity['parsed_content'] = content
                    except:
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
    
    analytics = UnifiedOutreachAnalytics()
    
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

if __name__ == "__main__":
    main()