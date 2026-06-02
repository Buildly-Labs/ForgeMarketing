#!/usr/bin/env python3
"""
Generic Marketing Calendar Seed Data
===================================

Seeds lightweight 30-day campaigns for active brands configured in the database.
This version intentionally avoids product-specific campaign naming/content.
"""

from datetime import datetime, timedelta, time
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.brand_loader import get_all_brands
from dashboard.marketing_calendar_models import (
    MarketingCalendar,
    MarketingTask,
    ContentTemplate,
    TaskType,
    TaskStatus,
    TaskPriority,
    PlatformType,
)
from dashboard.models import Brand
from dashboard.database import db


def _slugify(value: str) -> str:
    """Convert text to URL-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "campaign"


def _campaign_window() -> Tuple[datetime, datetime]:
    """Return campaign start/end dates for a 30-day window beginning next Monday."""
    now = datetime.utcnow()
    days_until_monday = (7 - now.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    start = datetime(now.year, now.month, now.day) + timedelta(days=days_until_monday)
    end = start + timedelta(days=30)
    return start, end


def _find_or_create_calendar(brand: Brand, start_date: datetime, end_date: datetime) -> Tuple[MarketingCalendar, bool]:
    """Create a generic 30-day campaign for a brand if one does not already exist."""
    campaign_slug = f"{brand.name}-growth-30d"
    existing = MarketingCalendar.query.filter_by(brand_name=brand.name, campaign_slug=campaign_slug).first()
    if existing:
        return existing, False

    campaign = MarketingCalendar(
        brand_name=brand.name,
        campaign_name=f"{brand.display_name} - 30 Day Growth Campaign",
        campaign_slug=campaign_slug,
        description=f"Generic 30-day multi-channel growth campaign for {brand.display_name}.",
        goal="Increase qualified leads and engagement",
        target_metric="Growth in brand engagement",
        start_date=start_date,
        end_date=end_date,
        budget=50.0,
        currency="USD",
        status="draft",
        owner="Growth Team",
        notes="Generated from generic marketing calendar seed routine.",
        meta_data={
            "source": "Generic Marketing Calendar Seeder",
            "channels": ["linkedin", "reddit", "devto", "youtube"],
            "cadence": "Weekly publish + engagement follow-ups",
        },
    )
    db.session.add(campaign)
    db.session.flush()
    return campaign, True


def _seed_tasks(calendar: MarketingCalendar, brand: Brand) -> int:
    """Seed a small reusable set of generic tasks for a campaign."""
    base_slug = f"{brand.name}-generic"
    existing = MarketingTask.query.filter(
        MarketingTask.calendar_id == calendar.id,
        MarketingTask.task_slug.like(f"{base_slug}%"),
    ).count()
    if existing:
        return 0

    week_1 = calendar.start_date

    tasks = [
        MarketingTask(
            calendar_id=calendar.id,
            brand_name=brand.name,
            task_name="LinkedIn Thought Leadership Post",
            task_slug=f"{base_slug}-linkedin-w1",
            description="Share one tactical lesson or result relevant to the brand audience.",
            task_type=TaskType.SOCIAL_POST,
            platform=PlatformType.LINKEDIN,
            scheduled_date=week_1,
            scheduled_time=time(hour=10, minute=0),
            assigned_to="growth-team",
            status=TaskStatus.DRAFT,
            priority=TaskPriority.HIGH,
            is_automated=False,
            title=f"What we learned this week at {brand.display_name}",
            body=(
                "Publish one practical insight from product, growth, or customer discovery. "
                "Include a short CTA to continue the conversation."
            ),
            meta_data={"channel_goal": "awareness", "estimated_reach": "500-5000"},
        ),
        MarketingTask(
            calendar_id=calendar.id,
            brand_name=brand.name,
            task_name="Community Post",
            task_slug=f"{base_slug}-community-w1",
            description="Post in a relevant community with a useful discussion prompt.",
            task_type=TaskType.SOCIAL_POST,
            platform=PlatformType.REDDIT,
            scheduled_date=week_1 + timedelta(days=2),
            scheduled_time=time(hour=9, minute=30),
            assigned_to="growth-team",
            status=TaskStatus.DRAFT,
            priority=TaskPriority.MEDIUM,
            is_automated=False,
            title=f"Feedback request from {brand.display_name}",
            body="Ask one concrete question and invite candid feedback from practitioners.",
            meta_data={"channel_goal": "engagement", "estimated_reach": "200-2000"},
        ),
        MarketingTask(
            calendar_id=calendar.id,
            brand_name=brand.name,
            task_name="Long-form Technical Article",
            task_slug=f"{base_slug}-article-w1",
            description="Publish one deeper technical or operational article.",
            task_type=TaskType.ARTICLE,
            platform=PlatformType.DEVTO,
            scheduled_date=week_1 + timedelta(days=4),
            scheduled_time=time(hour=8, minute=0),
            assigned_to="growth-team",
            status=TaskStatus.DRAFT,
            priority=TaskPriority.MEDIUM,
            is_automated=False,
            title=f"How {brand.display_name} approaches execution",
            body="Share a practical framework and include one actionable checklist.",
            meta_data={"channel_goal": "authority", "estimated_reach": "300-3000"},
        ),
        MarketingTask(
            calendar_id=calendar.id,
            brand_name=brand.name,
            task_name="Short-form Video",
            task_slug=f"{base_slug}-video-w1",
            description="Record a concise walkthrough or insight clip.",
            task_type=TaskType.VIDEO,
            platform=PlatformType.YOUTUBE,
            scheduled_date=week_1 + timedelta(days=6),
            scheduled_time=time(hour=12, minute=0),
            duration_minutes=20,
            assigned_to="growth-team",
            status=TaskStatus.DRAFT,
            priority=TaskPriority.MEDIUM,
            is_automated=False,
            title=f"Weekly walkthrough: {brand.display_name}",
            body="Create a 45-90 second clip with one core takeaway and clear CTA.",
            meta_data={"channel_goal": "reach", "duration_seconds": 60},
        ),
    ]

    for task in tasks:
        db.session.add(task)

    db.session.flush()
    return len(tasks)


def _seed_templates(brand: Brand) -> int:
    """Seed one generic social template per brand if missing."""
    template_slug = f"{brand.name}-thought-leadership-template"
    existing = ContentTemplate.query.filter_by(brand_name=brand.name, template_slug=template_slug).first()
    if existing:
        return 0

    template = ContentTemplate(
        brand_name=brand.name,
        template_name="Generic Thought Leadership Post",
        template_slug=template_slug,
        category="thought_leadership",
        platform=PlatformType.LINKEDIN,
        task_type=TaskType.SOCIAL_POST,
        title_template="{{headline}}",
        body_template=(
            "{{context}}\n\n"
            "What we changed:\n{{change_summary}}\n\n"
            "What happened:\n{{outcome}}\n\n"
            "{{cta}}"
        ),
        cta="Share your approach in the comments.",
        hashtags="#marketing #growth #execution",
        variables={
            "headline": f"A practical lesson from {brand.display_name}",
            "context": "Here is the problem we were trying to solve.",
            "change_summary": "One concrete change we made.",
            "outcome": "Observed result after the change.",
            "cta": "What would you test next?",
        },
        description="Generic reusable template for platform-native thought leadership posts.",
        usage_count=0,
    )

    db.session.add(template)
    db.session.flush()
    return 1


def seed_all_calendars(target_brands: Optional[List[str]] = None) -> bool:
    """Seed generic marketing calendars for active brands."""
    print("🚀 Seeding generic marketing calendars...\n")

    active_brand_names = get_all_brands(active_only=True)
    if target_brands:
        active_brand_names = [b for b in active_brand_names if b in set(target_brands)]

    if not active_brand_names:
        print("ℹ️ No active brands found. Complete onboarding or add brands in admin first.")
        return False

    start_date, end_date = _campaign_window()

    created_campaigns = 0
    created_tasks = 0
    created_templates = 0

    for brand_name in active_brand_names:
        brand = Brand.query.filter_by(name=brand_name).first()
        if not brand:
            continue

        calendar, is_new = _find_or_create_calendar(brand, start_date, end_date)
        if is_new:
            created_campaigns += 1

        task_count = _seed_tasks(calendar, brand)
        template_count = _seed_templates(brand)

        created_tasks += task_count
        created_templates += template_count

        print(f"✅ {brand.display_name}: +{task_count} task(s), +{template_count} template(s)")

    try:
        db.session.commit()
        print("\n✅ Generic calendar seed complete")
        print(f"   - Campaigns created: {created_campaigns}")
        print(f"   - Tasks created: {created_tasks}")
        print(f"   - Templates created: {created_templates}")
        return True
    except Exception as exc:
        db.session.rollback()
        print(f"\n❌ Error seeding calendars: {exc}")
        return False


def main() -> None:
    """CLI entrypoint."""
    from dashboard.app import app

    with app.app_context():
        seed_all_calendars()


if __name__ == "__main__":
    main()
