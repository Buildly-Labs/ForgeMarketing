#!/usr/bin/env python3
"""
Seed the database with brand configs, system settings, email configs, 
and API credential placeholders based on the original .env configuration.

Usage:
    python3 scripts/seed_database.py
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

os.chdir(project_root)

from dashboard.app import app
from dashboard.models import (
    db, Brand, BrandEmailConfig, BrandSettings,
    BrandAPICredential, SystemConfig
)


def seed_brands():
    """Seed default sample brands for a standalone workspace."""
    brands_data = [
        {
            'name': 'washoku',
            'display_name': 'Washoku',
            'description': 'A peaceful lifestyle companion for healthier eating, movement, sleep, and mindfulness habits.',
            'logo_url': '',
            'website_url': 'https://example.com/washoku',
        },
        {
            'name': 'northstar',
            'display_name': 'Northstar Labs',
            'description': 'B2B product studio sharing practical insights, feature releases, and customer wins.',
            'logo_url': '',
            'website_url': 'https://example.com/northstar',
        },
        {
            'name': 'sunnyside',
            'display_name': 'Sunnyside Goods',
            'description': 'Consumer lifestyle brand focused on practical habits, routines, and everyday products.',
            'logo_url': '',
            'website_url': 'https://example.com/sunnyside',
        },
        {
            'name': 'craftkit',
            'display_name': 'CraftKit',
            'description': 'Template and toolkit brand for creators and small teams launching digital products.',
            'logo_url': '',
            'website_url': 'https://example.com/craftkit',
        },
        {
            'name': 'trailhead',
            'display_name': 'Trailhead Studio',
            'description': 'Small agency model used as a sample for founder-led marketing operations workflows.',
            'logo_url': '',
            'website_url': 'https://example.com/trailhead',
        },
    ]

    created = 0
    for bd in brands_data:
        existing = Brand.query.filter_by(name=bd['name']).first()
        if existing:
            # Update existing brand with full info
            existing.display_name = bd['display_name']
            existing.description = bd['description']
            existing.logo_url = bd['logo_url']
            existing.website_url = bd['website_url']
            existing.is_active = True
            print(f"  Updated existing brand: {bd['display_name']}")
        else:
            brand = Brand(
                name=bd['name'],
                display_name=bd['display_name'],
                description=bd['description'],
                logo_url=bd['logo_url'],
                website_url=bd['website_url'],
                is_active=True,
            )
            db.session.add(brand)
            created += 1
            print(f"  Created brand: {bd['display_name']}")

    db.session.flush()
    print(f"  -> {created} new brands, {len(brands_data) - created} updated")


def seed_email_configs():
    """Seed email configurations for each brand"""
    configs = [
        {
            'brand_name': 'washoku',
            'provider': 'brevo',
            'api_key': '',  # Set via admin panel: MAILERSEND_API_TOKEN
            'from_email': 'team@washoku.example',
            'from_name': 'Washoku Team',
            'reply_to_email': 'team@washoku.example',
        },
        {
            'brand_name': 'northstar',
            'provider': 'brevo',
            'api_key': '',  # Set via admin panel: BREVO_API_KEY
            'smtp_host': 'smtp-relay.brevo.com',
            'smtp_port': 587,
            'smtp_user': '',  # Set via admin panel
            'from_email': 'team@northstar.example',
            'from_name': 'Northstar Team',
            'reply_to_email': 'team@northstar.example',
        },
        {
            'brand_name': 'sunnyside',
            'provider': 'brevo',
            'api_key': '',  # Set via admin panel: BREVO_API_KEY
            'smtp_host': 'smtp-relay.brevo.com',
            'smtp_port': 587,
            'smtp_user': '',  # Set via admin panel
            'from_email': 'team@sunnyside.example',
            'from_name': 'Sunnyside Team',
            'reply_to_email': 'team@sunnyside.example',
        },
        {
            'brand_name': 'craftkit',
            'provider': 'brevo',
            'api_key': '',  # Set via admin panel: BREVO_API_KEY
            'smtp_host': 'smtp-relay.brevo.com',
            'smtp_port': 587,
            'smtp_user': '',
            'from_email': 'team@craftkit.example',
            'from_name': 'CraftKit Team',
            'reply_to_email': 'team@craftkit.example',
        },
        {
            'brand_name': 'trailhead',
            'provider': 'brevo',
            'api_key': '',
            'smtp_host': 'smtp-relay.brevo.com',
            'smtp_port': 587,
            'smtp_user': '',
            'from_email': 'team@trailhead.example',
            'from_name': 'Trailhead Team',
            'reply_to_email': 'team@trailhead.example',
        },
    ]

    created = 0
    for cfg in configs:
        brand = Brand.query.filter_by(name=cfg['brand_name']).first()
        if not brand:
            print(f"  ⚠️  Brand {cfg['brand_name']} not found, skipping email config")
            continue

        existing = BrandEmailConfig.query.filter_by(
            brand_id=brand.id, provider=cfg['provider']
        ).first()
        if existing:
            print(f"  Email config already exists for {cfg['brand_name']}/{cfg['provider']}")
            continue

        ec = BrandEmailConfig(
            brand_id=brand.id,
            provider=cfg['provider'],
            api_key=cfg.get('api_key', ''),
            smtp_host=cfg.get('smtp_host', ''),
            smtp_port=cfg.get('smtp_port', 587),
            smtp_user=cfg.get('smtp_user', ''),
            from_email=cfg['from_email'],
            from_name=cfg['from_name'],
            reply_to_email=cfg.get('reply_to_email', ''),
            is_primary=True,
        )
        db.session.add(ec)
        created += 1
        print(f"  Created email config: {cfg['brand_name']} ({cfg['provider']})")

    print(f"  -> {created} email configs created")


def seed_brand_settings():
    """Seed default settings for each brand"""
    brands = Brand.query.all()
    created = 0
    for brand in brands:
        existing = BrandSettings.query.filter_by(brand_id=brand.id).first()
        if existing:
            print(f"  Settings already exist for {brand.name}")
            continue

        settings = BrandSettings(
            brand_id=brand.id,
            daily_email_limit=5000,
            enable_email_sending=True,
            enable_ai_generation=True,
            enable_social_posting=True,
        )
        db.session.add(settings)
        created += 1
        print(f"  Created settings for {brand.name}")

    print(f"  -> {created} brand settings created")


def seed_system_configs():
    """Seed system-wide configuration"""
    configs = [
        # AI Configuration
        ('ai_provider', 'ollama', 'AI provider (ollama or openai)', False, 'ai'),
        ('ai_model', 'llama3.2:1b', 'Default AI model', False, 'ai'),
        ('ai_ollama_url', 'http://localhost:11434', 'Ollama server URL', False, 'ai'),
        ('ai_openai_key', '', 'OpenAI API key (if using openai provider)', True, 'ai'),

        # General
        ('flask_env', 'development', 'Flask environment', False, 'general'),
        ('debug_mode', 'true', 'Enable debug mode', False, 'general'),
        ('log_level', 'INFO', 'Logging level', False, 'general'),
        ('daily_notification_email', 'team@example.com', 'Daily notification recipient', False, 'general'),

        # Google Ads (placeholders)
        ('google_ads_developer_token', '', 'Google Ads developer token', True, 'google_ads'),
        ('google_ads_client_id', '', 'Google Ads OAuth client ID', True, 'google_ads'),
        ('google_ads_client_secret', '', 'Google Ads OAuth client secret', True, 'google_ads'),

        # Google Analytics
        ('google_analytics_property_id', '', 'Google Analytics property ID', False, 'analytics'),
    ]

    created = 0
    for key, value, description, is_secret, category in configs:
        existing = SystemConfig.query.filter_by(key=key).first()
        if existing:
            print(f"  Config already exists: {key}")
            continue

        sc = SystemConfig(
            key=key,
            value=value,
            description=description,
            is_secret=is_secret,
            category=category,
            updated_by='seed_script',
        )
        db.session.add(sc)
        created += 1
        print(f"  Created config: {key} = {value if not is_secret else '***'}")

    print(f"  -> {created} system configs created")


def seed_api_credentials():
    """Seed API credential placeholders for each brand"""
    # Social credential placeholders for each sample brand
    twitter_brands = ['washoku', 'northstar', 'sunnyside', 'craftkit', 'trailhead']
    
    created = 0
    for brand_name in twitter_brands:
        brand = Brand.query.filter_by(name=brand_name).first()
        if not brand:
            continue

        # Twitter/X
        existing = BrandAPICredential.query.filter_by(
            brand_id=brand.id, service='twitter'
        ).first()
        if not existing:
            cred = BrandAPICredential(
                brand_id=brand.id,
                service='twitter',
                credential_type='oauth',
                credentials=json.dumps({
                    'api_key': '',
                    'api_secret': '',
                    'access_token': '',
                    'access_token_secret': '',
                    'bearer_token': '',
                }),
                is_active=False,
            )
            db.session.add(cred)
            created += 1
            print(f"  Created Twitter placeholder for {brand_name}")

        # LinkedIn
        existing = BrandAPICredential.query.filter_by(
            brand_id=brand.id, service='linkedin'
        ).first()
        if not existing:
            cred = BrandAPICredential(
                brand_id=brand.id,
                service='linkedin',
                credential_type='oauth',
                credentials=json.dumps({
                    'client_id': '',
                    'client_secret': '',
                }),
                is_active=False,
            )
            db.session.add(cred)
            created += 1
            print(f"  Created LinkedIn placeholder for {brand_name}")

        # BlueSky
        existing = BrandAPICredential.query.filter_by(
            brand_id=brand.id, service='bluesky'
        ).first()
        if not existing:
            cred = BrandAPICredential(
                brand_id=brand.id,
                service='bluesky',
                credential_type='api_key',
                credentials=json.dumps({
                    'username': '',
                    'app_password': '',
                }),
                is_active=False,
            )
            db.session.add(cred)
            created += 1
            print(f"  Created BlueSky placeholder for {brand_name}")

    print(f"  -> {created} API credential placeholders created")


def main():
    print("=" * 60)
    print("  ForgeMarketing Database Seeder")
    print("=" * 60)

    with app.app_context():
        db.create_all()

        print("\n📦 Seeding brands...")
        seed_brands()

        print("\n📧 Seeding email configurations...")
        seed_email_configs()

        print("\n⚙️  Seeding brand settings...")
        seed_brand_settings()

        print("\n🔧 Seeding system configurations...")
        seed_system_configs()

        print("\n🔑 Seeding API credential placeholders...")
        seed_api_credentials()

        db.session.commit()

        # Summary
        print("\n" + "=" * 60)
        print("  ✅ Database seeded successfully!")
        print("=" * 60)
        print(f"  Brands:            {Brand.query.count()}")
        print(f"  Email Configs:     {BrandEmailConfig.query.count()}")
        print(f"  Brand Settings:    {BrandSettings.query.count()}")
        print(f"  System Configs:    {SystemConfig.query.count()}")
        print(f"  API Credentials:   {BrandAPICredential.query.count()}")
        print()
        print("  ⚠️  API keys and secrets are set to empty placeholders.")
        print("  Use the Admin panel or setup wizard to enter real credentials.")
        print()


if __name__ == '__main__':
    main()
