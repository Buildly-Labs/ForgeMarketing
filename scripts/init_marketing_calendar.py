#!/usr/bin/env python3
"""
Quick start script to initialize marketing calendar with sample data.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta, time

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dashboard.app import app
from dashboard.database import DatabaseManager, db
from dashboard.models import Brand
from dashboard.marketing_calendar_models import (
    MarketingCalendar, MarketingTask, ContentTemplate, TaskType, 
    TaskStatus, TaskPriority, PlatformType
)


def init_marketing_calendar():
    """Initialize the marketing calendar with Washoku sample data"""
    
    print("\n🚀 Initializing Marketing Calendar System...")
    print("=" * 60)
    
    with app.app_context():
        # Initialize database first
        print("\n1️⃣  Initializing database...")
        db_manager = DatabaseManager(app)
        db_manager.init_db()
        print("   ✅ Database ready")
        
        # Verify brands exist
        print("\n2️⃣  Verifying brands...")
        brands = Brand.query.filter_by(is_active=True).all()
        if not brands:
            print("   ❌ No active brands found!")
            return False
        
        print(f"   ✅ Found {len(brands)} brands:")
        for brand in brands:
            print(f"      - {brand.name}: {brand.display_name}")
        
        # Create Washoku campaign
        print("\n3️⃣  Creating Washoku Campaign...")
        start_date = datetime.now().replace(day=6, hour=0, minute=0, second=0, microsecond=0)
        if start_date < datetime.now():
            start_date = start_date + timedelta(days=30)
        
        campaign = MarketingCalendar(
            brand_name='washoku',
            campaign_name='Washoku v1.2 Awareness Campaign',
            campaign_slug='washoku-v1-2-awareness',
            description='A calm awareness campaign for Washoku focused on peaceful habits, gentle logging, and balanced lifestyle content.',
            goal='Increase Washoku awareness and early signups',
            target_metric='1000 signups',
            start_date=start_date,
            end_date=start_date + timedelta(days=30),
            budget=20.0,
            currency='USD',
            status='draft',
            owner='Growth Team',
            notes='This is a human-reviewed awareness campaign using organic content and weekly review.',
            metadata={
                'source': 'Washoku sample seed data',
                'weekly_rhythm': 'Mon: Instagram, Tue: TikTok, Wed: YouTube Shorts, Thu: X, Fri: LinkedIn, Sat: Bluesky, Sun: Review',
                'special_events': ['Week 1 - Brand voice review', 'Week 2 - First analytics check'],
                'content_pillars': ['Peaceful meal habits', 'Sprout check-ins', 'Balance Garden progress']
            }
        )
        
        db.session.add(campaign)
        db.session.flush()
        print(f"   ✅ Campaign created (ID: {campaign.id})")
        
        # Create sample tasks for Week 1
        print("\n4️⃣  Creating Week 1 tasks...")
        
        tasks_data = [
            {
                'day_offset': 0,
                'hour': 9,
                'name': 'Reddit: Peaceful Meal Habits',
                'platform': PlatformType.REDDIT,
                'priority': TaskPriority.HIGH,
                'title': 'Real meals count too: a gentle reminder for Washoku users',
                'is_automated': False
            },
            {
                'day_offset': 1,
                'hour': 10,
                'name': 'LinkedIn: Sprout Check-in',
                'platform': PlatformType.LINKEDIN,
                'priority': TaskPriority.HIGH,
                'title': 'Meet Sprout, your gentle lifestyle companion',
                'is_automated': False
            },
            {
                'day_offset': 2,
                'hour': 8,
                'name': 'Dev.to: One-sentence logging',
                'platform': PlatformType.DEVTO,
                'priority': TaskPriority.HIGH,
                'title': 'One sentence meal logging with Washoku',
                'is_automated': False
            },
            {
                'day_offset': 3,
                'hour': 12,
                'name': 'YouTube: Real meals count',
                'platform': PlatformType.YOUTUBE,
                'priority': TaskPriority.MEDIUM,
                'title': 'Real meals count too',
                'is_automated': False
            },
            {
                'day_offset': 4,
                'hour': 14,
                'name': 'LinkedIn: Building without shame',
                'platform': PlatformType.LINKEDIN,
                'priority': TaskPriority.MEDIUM,
                'title': 'Building healthier habits without shame',
                'is_automated': False
            },
            {
                'day_offset': 5,
                'hour': 13,
                'name': 'Indie Hackers: Balance Garden progress',
                'platform': PlatformType.INDIE_HACKERS,
                'priority': TaskPriority.MEDIUM,
                'title': 'Your Balance Garden grows through small choices',
                'is_automated': False
            },
            {
                'day_offset': 4,  # Friday
                'hour': 10,
                'name': 'Hacker News: Recipe and plating ideas',
                'platform': PlatformType.HACKER_NEWS,
                'priority': TaskPriority.CRITICAL,
                'title': 'Recipe and plating ideas for calm, healthy meals',
                'is_automated': False
            }
        ]
        
        for task_data in tasks_data:
            task = MarketingTask(
                calendar_id=campaign.id,
                brand_name='washoku',
                task_name=task_data['name'],
                task_slug=task_data['name'].lower().replace(': ', '-').replace(' ', '-'),
                task_type=TaskType.SOCIAL_POST if task_data['platform'] != PlatformType.YOUTUBE else TaskType.VIDEO,
                platform=task_data['platform'],
                scheduled_date=start_date.replace(hour=task_data['hour']) + timedelta(days=task_data['day_offset']),
                scheduled_time=time(hour=task_data['hour'], minute=0),
                assigned_to='growth-team',
                status=TaskStatus.DRAFT,
                priority=task_data['priority'],
                is_automated=task_data['is_automated'],
                title=task_data['title'],
                body=f"Content for {task_data['name']} - Ready to create",
                meta_data={'platform': task_data['platform'].value}
            )
            db.session.add(task)
        
        db.session.flush()
        print(f"   ✅ Created {len(tasks_data)} tasks")
        
        # Create content templates
        print("\n5️⃣  Creating content templates...")
        
        templates = [
            ContentTemplate(
                brand_name='washoku',
                template_name='Reddit Post - Founder Pain',
                template_slug='reddit-founder-pain',
                category='social_proof',
                platform=PlatformType.REDDIT,
                task_type=TaskType.SOCIAL_POST,
                title_template='I built {{tool_name}} that {{main_benefit}} — can I get feedback?',
                body_template='Hey folks — {{origin_story}}\n\nSo I built a tool for that:\n👉 **{{tool_name}}** — {{tagline}}',
                cta='Try it free',
                hashtags='#startup #ai #productmanagement',
                variables={
                    'tool_name': 'Washoku',
                    'main_benefit': 'helps people build healthier habits gently',
                    'tagline': 'A peaceful lifestyle companion'
                },
                description='Template for social posts about peaceful habit building'
            ),
            ContentTemplate(
                brand_name='washoku',
                template_name='LinkedIn Post - Gentle Thought Leadership',
                template_slug='linkedin-thought-leadership',
                category='thought_leadership',
                platform=PlatformType.LINKEDIN,
                task_type=TaskType.SOCIAL_POST,
                title_template='{{headline}}',
                body_template='{{main_message}}\n\nSo we built {{solution}}',
                cta='Learn more',
                hashtags='#wellness #habits #health',
                variables={
                    'headline': 'Healthy habits work best when they feel gentle',
                    'main_message': 'People stay consistent when the system is calm and easy to return to',
                    'solution': 'a peaceful companion'
                },
                description='Template for Washoku thought leadership posts'
            )
        ]
        
        for template in templates:
            db.session.add(template)
        
        db.session.flush()
        print(f"   ✅ Created {len(templates)} templates")
        
        # Commit everything
        try:
            db.session.commit()
            print("\n✅ Marketing Calendar initialized successfully!")
            print("\n📊 Summary:")
            print(f"   - Campaign: Washoku v1.2 Awareness Campaign")
            print(f"   - Start Date: {start_date.strftime('%B %d, %Y')}")
            print(f"   - Tasks: {len(tasks_data)}")
            print(f"   - Templates: {len(templates)}")
            print(f"   - Platforms: Reddit, LinkedIn, Dev.to, YouTube, Indie Hackers, Hacker News")
            print("\n🚀 Next steps:")
            print("   1. Visit http://localhost:5003/marketing-calendar")
            print("   2. Review the Washoku campaign")
            print("   3. Assign tasks to team members")
            print("   4. Start executing from Monday")
            print("\n" + "=" * 60 + "\n")
            return True
        
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ Error: {e}")
            return False


if __name__ == '__main__':
    success = init_marketing_calendar()
    sys.exit(0 if success else 1)
