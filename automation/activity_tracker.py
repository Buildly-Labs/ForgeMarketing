#!/usr/bin/env python3
"""
Real-Time Activity Tracker
Tracks all AI content generation, email sends, campaign activities, and dashboard usage
Provides persistent storage and real-time analytics for the marketing automation dashboard

Supports SQLite, PostgreSQL, and MySQL via SQLAlchemy.
"""

import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging

from sqlalchemy import (create_engine, text, MetaData, Table, Column, Index,
                        Integer, String, Float, Boolean, Text, DateTime)


class ActivityTracker:
    """
    Comprehensive activity tracking system for marketing automation
    Tracks AI generation, emails, campaigns, dashboard usage, and analytics
    """
    
    def __init__(self, database_url: str = None):
        """Initialize activity tracker with database connection
        
        Args:
            database_url: SQLAlchemy database URL. Falls back to DATABASE_URL env var,
                         then to local SQLite file.
        """
        self.database_url = database_url or os.getenv('DATABASE_URL')
        
        if self.database_url:
            # Fix Heroku-style postgres:// -> postgresql://
            if self.database_url.startswith('postgres://'):
                self.database_url = self.database_url.replace('postgres://', 'postgresql://', 1)
            # Fix mysql:// -> mysql+mysqldb:// for mysqlclient driver
            if self.database_url.startswith('mysql://'):
                self.database_url = self.database_url.replace('mysql://', 'mysql+mysqldb://', 1)
            # Strip query params (e.g. ?ssl-mode=REQUIRED) that break mysqlclient
            if '?' in self.database_url:
                self.database_url = self.database_url.split('?')[0]
        else:
            db_path = str(Path(__file__).parent.parent / 'data' / 'activity_tracker.db')
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            self.database_url = f'sqlite:///{db_path}'
        
        self.engine = create_engine(self.database_url)
        self.sa_metadata = MetaData()
        self.logger = self._setup_logging()
        self._define_tables()
        self._initialize_database()
    
    def _setup_logging(self) -> logging.Logger:
        """Setup logging for activity tracker"""
        logger = logging.getLogger('ActivityTracker')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def _define_tables(self):
        """Define table schemas for cross-DB compatibility"""
        Table('ai_activity', self.sa_metadata,
            Column('id', Integer, primary_key=True, autoincrement=True),
            Column('timestamp', DateTime, server_default=text('CURRENT_TIMESTAMP')),
            Column('brand', String(255), nullable=False),
            Column('content_type', String(100), nullable=False),
            Column('template_used', String(255)),
            Column('prompt_tokens', Integer, default=0),
            Column('completion_tokens', Integer, default=0),
            Column('generation_time_ms', Integer, default=0),
            Column('quality_score', Float, default=0.0),
            Column('used_in_campaign', Boolean, default=False),
            Column('campaign_id', String(255)),
            Column('success', Boolean, default=True),
            Column('error_message', Text),
            Column('metadata', Text),
            Index('idx_ai_brand_time', 'brand', 'timestamp'),
        )
        
        Table('email_activity', self.sa_metadata,
            Column('id', Integer, primary_key=True, autoincrement=True),
            Column('timestamp', DateTime, server_default=text('CURRENT_TIMESTAMP')),
            Column('brand', String(255), nullable=False),
            Column('email_type', String(100), nullable=False),
            Column('campaign_id', String(255)),
            Column('recipient_email', String(255)),
            Column('subject', String(500)),
            Column('template_used', String(255)),
            Column('send_status', String(50), default='pending'),
            Column('delivery_time', DateTime),
            Column('opened', Boolean, default=False),
            Column('clicked', Boolean, default=False),
            Column('replied', Boolean, default=False),
            Column('unsubscribed', Boolean, default=False),
            Column('service_used', String(100)),
            Column('message_id', String(255)),
            Column('error_message', Text),
            Column('metadata', Text),
            Index('idx_email_brand_time', 'brand', 'timestamp'),
        )
        
        Table('campaign_activity', self.sa_metadata,
            Column('id', Integer, primary_key=True, autoincrement=True),
            Column('timestamp', DateTime, server_default=text('CURRENT_TIMESTAMP')),
            Column('brand', String(255), nullable=False),
            Column('campaign_id', String(255), nullable=False),
            Column('campaign_name', String(255)),
            Column('campaign_type', String(100)),
            Column('status', String(50), default='created'),
            Column('total_targets', Integer, default=0),
            Column('emails_sent', Integer, default=0),
            Column('emails_delivered', Integer, default=0),
            Column('responses_received', Integer, default=0),
            Column('conversion_rate', Float, default=0.0),
            Column('budget_spent', Float, default=0.0),
            Column('roi', Float, default=0.0),
            Column('start_time', DateTime),
            Column('end_time', DateTime),
            Column('metadata', Text),
            Index('idx_campaign_brand_time', 'brand', 'timestamp'),
        )
        
        Table('dashboard_activity', self.sa_metadata,
            Column('id', Integer, primary_key=True, autoincrement=True),
            Column('timestamp', DateTime, server_default=text('CURRENT_TIMESTAMP')),
            Column('page_visited', String(255)),
            Column('action_taken', String(100)),
            Column('brand_context', String(255)),
            Column('user_agent', Text),
            Column('ip_address', String(45)),
            Column('session_duration', Integer, default=0),
            Column('api_endpoint', String(255)),
            Column('response_time_ms', Integer, default=0),
            Column('success', Boolean, default=True),
            Column('error_message', Text),
            Column('metadata', Text),
            Index('idx_dashboard_time', 'timestamp'),
        )
        
        Table('system_metrics', self.sa_metadata,
            Column('id', Integer, primary_key=True, autoincrement=True),
            Column('timestamp', DateTime, server_default=text('CURRENT_TIMESTAMP')),
            Column('metric_type', String(100), nullable=False),
            Column('metric_name', String(255), nullable=False),
            Column('metric_value', Float),
            Column('metric_unit', String(50)),
            Column('brand_context', String(255)),
            Column('time_period', String(20)),
            Column('metadata', Text),
            Index('idx_metrics_type_time', 'metric_type', 'timestamp'),
        )
    
    def _initialize_database(self):
        """Create all tables if they don't exist"""
        self.sa_metadata.create_all(self.engine, checkfirst=True)
        self.logger.info("✅ Activity tracking database initialized")
    
    # AI Activity Tracking
    def track_ai_generation(self, brand: str, content_type: str, template_used: str = None, 
                           prompt_tokens: int = 0, completion_tokens: int = 0, 
                           generation_time_ms: int = 0, quality_score: float = 0.0, 
                           success: bool = True, error_message: str = None, 
                           metadata: Dict = None) -> int:
        """Track AI content generation activity"""
        with self.engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO ai_activity 
                (brand, content_type, template_used, prompt_tokens, completion_tokens, 
                 generation_time_ms, quality_score, success, error_message, metadata)
                VALUES (:brand, :content_type, :template_used, :prompt_tokens, :completion_tokens,
                        :generation_time_ms, :quality_score, :success, :error_message, :metadata)
            """), {
                'brand': brand, 'content_type': content_type, 'template_used': template_used,
                'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens,
                'generation_time_ms': generation_time_ms, 'quality_score': quality_score,
                'success': success, 'error_message': error_message,
                'metadata': json.dumps(metadata) if metadata else None
            })
            activity_id = result.lastrowid or 0
            
        self.logger.info(f"🤖 Tracked AI generation: {brand} - {content_type}")
        return activity_id
    
    def track_email_send(self, brand: str, email_type: str, recipient_email: str = None,
                        subject: str = None, template_used: str = None, 
                        campaign_id: str = None, service_used: str = None,
                        send_status: str = 'sent', message_id: str = None,
                        error_message: str = None, metadata: Dict = None) -> int:
        """Track email sending activity"""
        with self.engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO email_activity 
                (brand, email_type, campaign_id, recipient_email, subject, template_used,
                 send_status, service_used, message_id, error_message, metadata)
                VALUES (:brand, :email_type, :campaign_id, :recipient_email, :subject, :template_used,
                        :send_status, :service_used, :message_id, :error_message, :metadata)
            """), {
                'brand': brand, 'email_type': email_type, 'campaign_id': campaign_id,
                'recipient_email': recipient_email, 'subject': subject, 'template_used': template_used,
                'send_status': send_status, 'service_used': service_used, 'message_id': message_id,
                'error_message': error_message,
                'metadata': json.dumps(metadata) if metadata else None
            })
            activity_id = result.lastrowid or 0
            
        self.logger.info(f"📧 Tracked email send: {brand} - {email_type} to {recipient_email}")
        return activity_id
    
    def track_campaign_activity(self, brand: str, campaign_id: str, campaign_name: str = None,
                               campaign_type: str = None, status: str = 'created',
                               total_targets: int = 0, emails_sent: int = 0,
                               metadata: Dict = None) -> int:
        """Track campaign creation and updates"""
        with self.engine.begin() as conn:
            # Check if campaign already exists
            result = conn.execute(
                text("SELECT id FROM campaign_activity WHERE campaign_id = :campaign_id"),
                {'campaign_id': campaign_id}
            )
            existing = result.fetchone()
            
            if existing:
                conn.execute(text("""
                    UPDATE campaign_activity SET
                    status = :status, total_targets = :total_targets, emails_sent = :emails_sent, 
                    metadata = :metadata, timestamp = CURRENT_TIMESTAMP
                    WHERE campaign_id = :campaign_id
                """), {
                    'status': status, 'total_targets': total_targets, 'emails_sent': emails_sent,
                    'metadata': json.dumps(metadata) if metadata else None,
                    'campaign_id': campaign_id
                })
                activity_id = existing[0]
            else:
                result = conn.execute(text("""
                    INSERT INTO campaign_activity 
                    (brand, campaign_id, campaign_name, campaign_type, status,
                     total_targets, emails_sent, metadata)
                    VALUES (:brand, :campaign_id, :campaign_name, :campaign_type, :status,
                            :total_targets, :emails_sent, :metadata)
                """), {
                    'brand': brand, 'campaign_id': campaign_id, 'campaign_name': campaign_name,
                    'campaign_type': campaign_type, 'status': status,
                    'total_targets': total_targets, 'emails_sent': emails_sent,
                    'metadata': json.dumps(metadata) if metadata else None
                })
                activity_id = result.lastrowid or 0
            
        self.logger.info(f"📊 Tracked campaign activity: {brand} - {campaign_id} ({status})")
        return activity_id
    
    def track_dashboard_usage(self, page_visited: str, action_taken: str = 'view',
                             brand_context: str = None, api_endpoint: str = None,
                             response_time_ms: int = 0, success: bool = True,
                             error_message: str = None, metadata: Dict = None) -> int:
        """Track dashboard usage and interactions"""
        with self.engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO dashboard_activity 
                (page_visited, action_taken, brand_context, api_endpoint,
                 response_time_ms, success, error_message, metadata)
                VALUES (:page_visited, :action_taken, :brand_context, :api_endpoint,
                        :response_time_ms, :success, :error_message, :metadata)
            """), {
                'page_visited': page_visited, 'action_taken': action_taken,
                'brand_context': brand_context, 'api_endpoint': api_endpoint,
                'response_time_ms': response_time_ms, 'success': success,
                'error_message': error_message,
                'metadata': json.dumps(metadata) if metadata else None
            })
            activity_id = result.lastrowid or 0
            
        return activity_id
    
    def update_system_metric(self, metric_type: str, metric_name: str, 
                            metric_value: float, metric_unit: str = 'count',
                            brand_context: str = None, time_period: str = '24h',
                            metadata: Dict = None):
        """Update system performance metrics"""
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO system_metrics 
                (metric_type, metric_name, metric_value, metric_unit,
                 brand_context, time_period, metadata)
                VALUES (:metric_type, :metric_name, :metric_value, :metric_unit,
                        :brand_context, :time_period, :metadata)
            """), {
                'metric_type': metric_type, 'metric_name': metric_name,
                'metric_value': metric_value, 'metric_unit': metric_unit,
                'brand_context': brand_context, 'time_period': time_period,
                'metadata': json.dumps(metadata) if metadata else None
            })
    
    # Analytics and Reporting Methods
    def get_real_time_dashboard_data(self, hours_back: int = 24) -> Dict[str, Any]:
        """Get real-time dashboard data for the specified time period"""
        cutoff_time = datetime.now() - timedelta(hours=hours_back)
        
        with self.engine.connect() as conn:
            # AI Generation Stats
            result = conn.execute(text("""
                SELECT brand, COUNT(*) as generations, 
                       AVG(prompt_tokens + completion_tokens) as avg_tokens,
                       AVG(generation_time_ms) as avg_time_ms,
                       AVG(quality_score) as avg_quality,
                       SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful_generations
                FROM ai_activity 
                WHERE timestamp >= :cutoff
                GROUP BY brand
            """), {'cutoff': cutoff_time})
            
            ai_stats = {}
            for row in result.fetchall():
                brand, generations, avg_tokens, avg_time_ms, avg_quality, successful = row
                ai_stats[brand] = {
                    'total_generations': generations,
                    'avg_tokens': round(avg_tokens or 0, 2),
                    'avg_generation_time_ms': round(avg_time_ms or 0, 2),
                    'avg_quality_score': round(avg_quality or 0, 2),
                    'success_rate': round((successful / generations * 100) if generations > 0 else 0, 2)
                }
            
            # Email Activity Stats
            result = conn.execute(text("""
                SELECT brand, email_type, COUNT(*) as count,
                       SUM(CASE WHEN send_status = 'delivered' THEN 1 ELSE 0 END) as delivered,
                       SUM(CASE WHEN opened THEN 1 ELSE 0 END) as opened,
                       SUM(CASE WHEN clicked THEN 1 ELSE 0 END) as clicked
                FROM email_activity 
                WHERE timestamp >= :cutoff
                GROUP BY brand, email_type
            """), {'cutoff': cutoff_time})
            
            email_stats = {}
            for row in result.fetchall():
                brand, email_type, count, delivered, opened, clicked = row
                if brand not in email_stats:
                    email_stats[brand] = {}
                
                email_stats[brand][email_type] = {
                    'total_sent': count,
                    'delivered': delivered,
                    'opened': opened,
                    'clicked': clicked,
                    'delivery_rate': round((delivered / count * 100) if count > 0 else 0, 2),
                    'open_rate': round((opened / delivered * 100) if delivered > 0 else 0, 2),
                    'click_rate': round((clicked / delivered * 100) if delivered > 0 else 0, 2)
                }
            
            # Campaign Stats
            result = conn.execute(text("""
                SELECT brand, COUNT(*) as campaigns,
                       SUM(emails_sent) as total_emails,
                       SUM(responses_received) as total_responses,
                       AVG(conversion_rate) as avg_conversion_rate
                FROM campaign_activity 
                WHERE timestamp >= :cutoff
                GROUP BY brand
            """), {'cutoff': cutoff_time})
            
            campaign_stats = {}
            for row in result.fetchall():
                brand, campaigns, total_emails, total_responses, avg_conversion_rate = row
                campaign_stats[brand] = {
                    'active_campaigns': campaigns,
                    'total_emails_sent': total_emails or 0,
                    'total_responses': total_responses or 0,
                    'avg_conversion_rate': round(avg_conversion_rate or 0, 2),
                    'response_rate': round((total_responses / total_emails * 100) if total_emails > 0 else 0, 2)
                }
            
            # Dashboard Usage Stats
            result = conn.execute(text("""
                SELECT COUNT(*) as page_views,
                       COUNT(DISTINCT page_visited) as unique_pages,
                       AVG(response_time_ms) as avg_response_time,
                       SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful_requests
                FROM dashboard_activity 
                WHERE timestamp >= :cutoff
            """), {'cutoff': cutoff_time})
            
            dashboard_stats = result.fetchone()
            page_views, unique_pages, avg_response_time, successful_requests = dashboard_stats
            
            # Overall Summary
            summary = {
                'timestamp': datetime.now().isoformat(),
                'period_hours': hours_back,
                'ai_activity': ai_stats,
                'email_activity': email_stats,
                'campaign_activity': campaign_stats,
                'dashboard_performance': {
                    'total_page_views': page_views,
                    'unique_pages_visited': unique_pages,
                    'avg_response_time_ms': round(avg_response_time or 0, 2),
                    'success_rate': round((successful_requests / page_views * 100) if page_views > 0 else 0, 2)
                },
                'system_health': {
                    'database_url': self.database_url.split('@')[-1] if '@' in self.database_url else self.database_url,
                    'data_collection_active': True,
                    'last_updated': datetime.now().isoformat()
                }
            }
            
        return summary
    
    def get_brand_activity_summary(self, brand: str, days_back: int = 30) -> Dict[str, Any]:
        """Get comprehensive activity summary for a specific brand"""
        cutoff_time = datetime.now() - timedelta(days=days_back)
        
        with self.engine.connect() as conn:
            # AI Generation Activity
            result = conn.execute(text("""
                SELECT content_type, COUNT(*) as count,
                       AVG(quality_score) as avg_quality,
                       SUM(prompt_tokens + completion_tokens) as total_tokens
                FROM ai_activity 
                WHERE brand = :brand AND timestamp >= :cutoff
                GROUP BY content_type
            """), {'brand': brand, 'cutoff': cutoff_time})
            
            ai_activity = {}
            for row in result.fetchall():
                content_type, count, avg_quality, total_tokens = row
                ai_activity[content_type] = {
                    'generations': count,
                    'avg_quality': round(avg_quality or 0, 2),
                    'total_tokens': total_tokens or 0
                }
            
            # Email Activity
            result = conn.execute(text("""
                SELECT email_type, COUNT(*) as sent,
                       SUM(CASE WHEN send_status = 'delivered' THEN 1 ELSE 0 END) as delivered,
                       SUM(CASE WHEN opened THEN 1 ELSE 0 END) as opened
                FROM email_activity 
                WHERE brand = :brand AND timestamp >= :cutoff
                GROUP BY email_type
            """), {'brand': brand, 'cutoff': cutoff_time})
            
            email_activity = {}
            for row in result.fetchall():
                email_type, sent, delivered, opened = row
                email_activity[email_type] = {
                    'sent': sent,
                    'delivered': delivered,
                    'opened': opened,
                    'open_rate': round((opened / delivered * 100) if delivered > 0 else 0, 2)
                }
            
            # Campaign Activity
            result = conn.execute(text("""
                SELECT COUNT(*) as campaigns,
                       SUM(total_targets) as targets,
                       SUM(emails_sent) as emails,
                       SUM(responses_received) as responses
                FROM campaign_activity 
                WHERE brand = :brand AND timestamp >= :cutoff
            """), {'brand': brand, 'cutoff': cutoff_time})
            
            campaign_data = result.fetchone()
            campaigns, targets, emails, responses = campaign_data
            
            return {
                'brand': brand,
                'period_days': days_back,
                'ai_activity': ai_activity,
                'email_activity': email_activity,
                'campaign_summary': {
                    'total_campaigns': campaigns or 0,
                    'total_targets': targets or 0,
                    'total_emails': emails or 0,
                    'total_responses': responses or 0,
                    'response_rate': round((responses / emails * 100) if emails or 0 > 0 else 0, 2)
                },
                'last_updated': datetime.now().isoformat()
            }


def main():
    """Test the activity tracker"""
    tracker = ActivityTracker()
    
    # Test tracking some activities
    print("🧪 Testing Activity Tracker...")
    
    # Track AI generation
    tracker.track_ai_generation(
        brand='foundry',
        content_type='email',
        template_used='outreach',
        prompt_tokens=150,
        completion_tokens=300,
        generation_time_ms=1200,
        quality_score=8.5,
        success=True,
        metadata={'campaign_id': 'test_campaign_001'}
    )
    
    # Track email send
    tracker.track_email_send(
        brand='foundry',
        email_type='outreach',
        recipient_email='test@example.com',
        subject='Test Outreach Email',
        template_used='general_outreach',
        campaign_id='test_campaign_001',
        service_used='brevo',
        send_status='delivered'
    )
    
    # Track campaign
    tracker.track_campaign_activity(
        brand='foundry',
        campaign_id='test_campaign_001',
        campaign_name='Test Campaign',
        campaign_type='outreach',
        status='running',
        total_targets=100,
        emails_sent=50
    )
    
    # Get real-time data
    dashboard_data = tracker.get_real_time_dashboard_data(24)
    print("\n📊 Real-time Dashboard Data:")
    print(json.dumps(dashboard_data, indent=2))
    
    # Get brand summary
    brand_summary = tracker.get_brand_activity_summary('foundry', 7)
    print(f"\n🏢 Brand Summary for Foundry:")
    print(json.dumps(brand_summary, indent=2))
    
    print("\n✅ Activity tracker test completed!")


if __name__ == "__main__":
    main()