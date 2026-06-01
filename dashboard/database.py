"""
Database initialization and migration utilities
"""

import os
from pathlib import Path
from datetime import datetime
from dashboard.models import (
    db, Brand, BrandEmailConfig, BrandSettings, BrandAPICredential,
    SystemConfig, APICredentialLog, User, UserBrand, BrandTheme,
)


class DatabaseManager:
    """Manages database initialization and migrations"""
    
    def __init__(self, app):
        self.app = app
        self._db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
        self._is_sqlite = self._db_uri.startswith('sqlite')
    
    @property
    def db_path(self):
        """Get the SQLite file path (only meaningful for SQLite databases)"""
        if self._is_sqlite:
            return Path(self._db_uri.replace('sqlite:///', ''))
        return None
    
    def init_db(self) -> bool:
        """Initialize database with schema (no default brands).

        Retries once on transient concurrent-DDL errors that occur when
        multiple gunicorn workers race to initialise the same tables.
        """
        import time
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                with self.app.app_context():
                    db.create_all()
                    self._apply_schema_migrations()
                    print("✅ Database schema initialized successfully")

                    # Seed admin user if the DB is empty; brands are created via onboarding
                    brand_count = Brand.query.count()
                    user_count = User.query.count()
                    if user_count == 0:
                        self._seed_admin_user()
                    else:
                        self._sync_admin_user()

                    # Seed system config defaults (idempotent – skips existing keys)
                    self._seed_system_configs()

                    brand_count = Brand.query.count()
                    if brand_count == 0:
                        print("ℹ️  No brands configured. Complete onboarding to add brands.")
                    else:
                        print(f"✅ Found {brand_count} existing brand(s)")

                    return True
            except Exception as e:
                msg = str(e)
                if attempt < max_attempts and ('concurrent DDL' in msg or 'being modified' in msg):
                    print(f"⚠️  Concurrent DDL detected (attempt {attempt}/{max_attempts}), retrying…")
                    time.sleep(2 * attempt)
                    continue
                print(f"❌ Database initialization failed: {e}")
                return False
        return False

    # ── Schema migrations (lightweight ALTER TABLE for MySQL) ──

    def _apply_schema_migrations(self) -> None:
        """Add missing columns to existing tables.
        
        SQLAlchemy's create_all() only creates new tables — it won't add
        new columns to tables that already exist.  This method inspects
        the live schema and runs ALTER TABLE for any columns the models
        define but the database doesn't have yet.
        """
        from sqlalchemy import inspect as sa_inspect, text

        inspector = sa_inspect(db.engine)
        migrations = [
            # (table, column_name, column_sql_type)
            ('users', 'must_change_password', 'BOOLEAN DEFAULT 0'),
        ]

        for table, col, col_type in migrations:
            if not inspector.has_table(table):
                continue
            existing = {c['name'] for c in inspector.get_columns(table)}
            if col not in existing:
                stmt = f'ALTER TABLE `{table}` ADD COLUMN `{col}` {col_type}'
                db.session.execute(text(stmt))
                db.session.commit()
                print(f"  ↳ Added column {table}.{col}")

    # ── Seed helpers ─────────────────────────────────────────

    def _seed_brands_and_themes(self) -> None:
        """Legacy hook retained for compatibility; default brand seeding is disabled."""
        print("ℹ️  Default brand seeding is disabled. Add brands from onboarding or admin.")

    def _seed_admin_user(self) -> None:
        """Create a default admin user linked to all brands."""
        admin_email = os.getenv('ADMIN_EMAIL', 'admin@firstcityfoundry.com')
        admin_password = os.getenv('ADMIN_PASSWORD', 'changeme')

        user = User(email=admin_email, display_name='Admin', is_admin=True, must_change_password=True)
        user.set_password(admin_password)
        db.session.add(user)
        db.session.flush()

        # Link to every active brand
        for brand in Brand.query.filter_by(is_active=True).all():
            db.session.add(UserBrand(user_id=user.id, brand_id=brand.id, role='owner'))

        # Mark setup as complete so onboarding check passes
        if not SystemConfig.query.filter_by(key='setup_completed').first():
            db.session.add(SystemConfig(
                key='setup_completed',
                value='{"completed": true, "source": "seed"}',
                category='system',
                description='Seeded during initial setup',
            ))

        db.session.commit()
        print(f"✅ Seeded admin user: {admin_email}  (change password immediately!)")

    def _sync_admin_user(self) -> None:
        """Update existing admin user credentials from env vars if set."""
        admin_email = os.getenv('ADMIN_EMAIL', '').strip()
        admin_password = os.getenv('ADMIN_PASSWORD', '').strip()
        if not admin_email or not admin_password:
            return

        user = User.query.filter_by(is_admin=True).first()
        if not user:
            return

        changed = False
        if user.email != admin_email:
            user.email = admin_email
            changed = True
        if not user.check_password(admin_password):
            user.set_password(admin_password)
            changed = True

        if changed:
            db.session.commit()
            print(f"✅ Synced admin credentials from env vars: {admin_email}")

    def _seed_system_configs(self) -> None:
        """Seed SystemConfig rows from env vars (idempotent – skips keys that already exist)."""
        defaults = [
            # Email / SMTP
            ('BREVO_SMTP_KEY',   'email', True),
            ('BREVO_SMTP_LOGIN', 'email', False),
            ('BREVO_SMTP_HOST',  'email', False),
            ('BREVO_SMTP_PORT',  'email', False),
            ('FROM_EMAIL',       'email', False),
            ('FROM_NAME',        'email', False),
            ('REPLY_TO_EMAIL',   'email', False),
            # AI
            ('OPENAI_API_KEY',   'ai', True),
            ('OPENAI_MODEL',     'ai', False),
            ('OLLAMA_HOST',      'ai', False),
            # Social
            ('TWITTER_API_KEY',             'social', True),
            ('TWITTER_API_SECRET',          'social', True),
            ('TWITTER_ACCESS_TOKEN',        'social', True),
            ('TWITTER_ACCESS_TOKEN_SECRET', 'social', True),
            ('LINKEDIN_CLIENT_ID',          'social', False),
            ('LINKEDIN_CLIENT_SECRET',      'social', True),
            # Analytics
            ('GOOGLE_ANALYTICS_PROPERTY_ID','analytics', False),
            ('GOOGLE_ANALYTICS_API_KEY',    'analytics', True),
            ('YOUTUBE_CHANNEL_ID',          'analytics', False),
            ('YOUTUBE_API_KEY',             'analytics', True),
            # Notifications
            ('DAILY_NOTIFICATION_EMAIL',    'notifications', False),
            ('DAILY_CC_EMAIL',              'notifications', False),
            ('PUSHOVER_USER_KEY',           'notifications', True),
            ('PUSHOVER_API_TOKEN',          'notifications', True),
            # Outreach
            ('MAX_DAILY_OUTREACH',   'outreach', False),
            ('MAX_PER_ORGANIZATION', 'outreach', False),
            ('MIN_DELAY_SECONDS',    'outreach', False),
            ('MAX_DELAY_SECONDS',    'outreach', False),
            # Site
            ('WEBSITE_URL', 'site', False),
            ('SITE_NAME',   'site', False),
        ]

        added = 0
        for key, category, is_secret in defaults:
            if SystemConfig.query.filter_by(key=key).first():
                continue
            env_val = os.getenv(key, '')
            db.session.add(SystemConfig(
                key=key,
                value=env_val,
                category=category,
                is_secret=is_secret,
                description=f'Auto-seeded from environment',
                updated_by='seed',
            ))
            added += 1

        if added:
            db.session.commit()
            print(f"✅ Seeded {added} system config entries from environment")
    
    def _load_default_brands(self) -> None:
        """Legacy hook retained for compatibility; default brand loading is disabled."""
        print("ℹ️  No default brands are loaded during reset. Configure brands manually.")
    
    def reset_db(self) -> bool:
        """Drop all tables and recreate (DESTRUCTIVE!)"""
        try:
            with self.app.app_context():
                db.drop_all()
                db.create_all()
                self._load_default_brands()
                print("✅ Database reset successfully")
                return True
        except Exception as e:
            print(f"❌ Database reset failed: {e}")
            return False
    
    @staticmethod
    def backup_db(source_path: str, backup_path: str) -> bool:
        """Backup SQLite database file. For PostgreSQL/MySQL, use native dump tools."""
        try:
            import shutil
            if not os.path.exists(source_path):
                print(f"⚠️  Source database not found: {source_path}")
                return False
            shutil.copy(source_path, backup_path)
            print(f"✅ Database backed up to {backup_path}")
            return True
        except Exception as e:
            print(f"❌ Backup failed: {e}")
            return False
