# Admin Panel & Database Integration Guide

## Overview

The marketing automation dashboard has been migrated from hardcoded environment variables to a **database-backed multi-tenant architecture**. This enables:

- **Dynamic brand management** - Add/edit brands without redeployment
- **Multi-provider support** - Brevo, MailerSend, SendGrid, Mailgun per brand
- **Admin UI** - Web interface for managing brands and configurations
- **Audit logging** - Track all API credential access and changes
- **Real data only** - No mock data, all configurations use real credentials

## Quick Start

### 1. Initialize Database

```bash
cd /Users/greglind/Projects/me/marketing
python dashboard/init_db.py
```

This will:
- Create `marketing_dashboard.db` SQLite database
- Initialize schema with Brand, BrandEmailConfig, BrandSettings, and APICredentialLog tables
- Keep brand list dynamic (brands are created via onboarding/admin flows)
- Store provider configuration per brand in the database

### 2. Start Dashboard

```bash
cd /Users/greglind/Projects/me/marketing
python dashboard/app.py
```

Then navigate to:
- **Admin Panel**: `http://localhost:5000/admin/brands`
- **Main Dashboard**: `http://localhost:5000/`

## Database Architecture

### Models

#### Brand
Represents a brand managed in the system.

**Fields:**
- `id` - Primary key
- `name` - Unique identifier (brand slug, e.g. `washokuplus`)
- `display_name` - Human-readable name
- `description` - Brand description
- `logo_url` - Brand logo
- `website_url` - Brand website
- `is_active` - Active/inactive status
- `created_at`, `updated_at` - Timestamps

**Relationships:**
- One-to-many with `BrandEmailConfig` (multiple providers per brand)
- One-to-one with `BrandSettings`

#### BrandEmailConfig
Email provider configuration for each brand.

**Fields:**
- `brand_id` - Foreign key to Brand
- `provider` - brevo, mailersend, sendgrid, mailgun
- `api_key` - Provider API key (encrypted in production)
- `api_token` - Provider API token
- `from_email` - Email address emails are sent from
- `from_name` - Display name for sender
- `is_primary` - Is this the primary provider?
- `is_verified` - Has this provider been verified?
- `max_send_per_day` - Daily send limit for this provider
- `rate_limit_per_minute` - Messages per minute limit
- `emails_sent_today` - Counter for daily limit
- `contact_lists` - JSON with provider contact list IDs
- `created_at`, `updated_at` - Timestamps

**Unique Constraint:** (brand_id, provider) - Only one config per provider per brand

#### BrandSettings
Brand-specific configuration and feature flags.

**Fields:**
- `brand_id` - Foreign key to Brand
- `daily_email_limit` - Maximum emails sent daily across all providers
- `enable_email_sending` - Toggle email functionality
- `enable_ai_generation` - Toggle AI content generation
- `enable_social_posting` - Toggle social media posting
- `auto_subscribe_new_contacts` - Auto-subscribe new contacts
- `auto_unsubscribe_invalid` - Auto-unsubscribe invalid emails
- `default_campaign_type` - Default campaign template
- `default_send_time` - Default send time HH:MM format
- `default_send_day_of_week` - 0-6 (Sunday-Saturday)
- `enable_analytics_tracking` - Track open/click rates
- `enable_utm_parameters` - Add UTM tracking parameters
- `advanced_settings` - JSON for extensibility
- `created_at`, `updated_at` - Timestamps

#### APICredentialLog
Audit trail for all credential access and changes.

**Fields:**
- `id` - Primary key
- `brand_id` - Foreign key to Brand
- `email_config_id` - Foreign key to BrandEmailConfig (nullable)
- `action` - created, updated, accessed, tested, rotated, deleted
- `action_by` - User who performed action (defaults to "system")
- `ip_address` - IP address of user
- `user_agent` - Browser/client information
- `success` - Did the action succeed?
- `error_message` - Error details if failed
- `created_at` - When action occurred

## Admin API Endpoints

### Brand Management

#### List All Brands
```
GET /api/admin/brands
Response: {
  "success": true,
  "brands": [
    {
      "id": 1,
      "name": "washokuplus",
      "display_name": "Washoku Plus",
      "is_active": true,
      "email_providers": [{"provider": "mailersend", "is_primary": true}]
    }
  ],
  "total": 5
}
```

#### Get Brand Details
```
GET /api/admin/brands/<brand_name>
Response: {
  "success": true,
  "brand": { ... },
  "email_configs": [ ... ],
  "settings": { ... },
  "activity_logs": [ ... ]
}
```

#### Create Brand
```
POST /api/admin/brands
{
  "name": "mynewbrand",
  "display_name": "My New Brand",
  "description": "Brand description",
  "website_url": "https://example.com",
  "is_active": true
}
```

#### Update Brand
```
PUT /api/admin/brands/<brand_name>
{
  "display_name": "Updated Name",
  "is_active": true
}
```

### Email Configuration Management

#### List Email Configs
```
GET /api/admin/brands/<brand_name>/email-configs
Response: {
  "success": true,
  "configs": [
    {
      "id": 1,
      "provider": "brevo",
      "from_email": "team@open.build",
      "is_primary": true,
      "is_verified": true
    }
  ]
}
```

#### Add Email Config
```
POST /api/admin/brands/<brand_name>/email-configs
{
  "provider": "brevo",
  "api_key": "xkeysib-xxx...",
  "from_email": "team@open.build",
  "from_name": "OpenBuild Team",
  "max_send_per_day": 10000
}
```

#### Update Email Config
```
PUT /api/admin/brands/<brand_name>/email-configs/<provider>
{
  "from_email": "newemail@open.build",
  "max_send_per_day": 5000
}
```

#### Delete Email Config
```
DELETE /api/admin/brands/<brand_name>/email-configs/<provider>
```

### Settings Management

#### Get Settings
```
GET /api/admin/brands/<brand_name>/settings
Response: {
  "success": true,
  "settings": {
    "daily_email_limit": 50000,
    "enable_email_sending": true,
    "enable_ai_generation": true
  }
}
```

#### Update Settings
```
PUT /api/admin/brands/<brand_name>/settings
{
  "daily_email_limit": 25000,
  "enable_email_sending": true,
  "enable_ai_generation": false
}
```

### Audit Logs

#### Get Audit Trail
```
GET /api/admin/audit-logs/<brand_name>?limit=50&offset=0
Response: {
  "success": true,
  "logs": [
    {
      "id": 1,
      "brand_id": 1,
      "action": "created",
      "action_by": "system",
      "success": true,
      "created_at": "2025-01-15T10:30:00"
    }
  ]
}
```

## Admin UI Features

### Brands Tab
- View all active brands
- Card-based interface showing:
  - Brand name and description
  - Active/Inactive status
  - Number of email configurations
  - Edit and delete options

### Email Configs Tab
- Table view of all email provider configurations
- Columns: Brand, Provider, From Email, Primary, Verified
- Actions: Edit, Test, Delete

### Audit Logs Tab
- Recent system activity
- Shows: Action type, brand, timestamp, success/failure
- Color-coded for quick scanning

## Integrating with Email Analytics

### Before (Environment Variables)
```python
brand_config = os.getenv('BREVO_API_KEY')  # Hardcoded per brand
```

### After (Database)
```python
from dashboard.models import Brand, BrandEmailConfig

# Get brand and primary email config
brand = Brand.query.filter_by(name='openbuild').first()
email_config = brand.email_configs.filter_by(is_primary=True).first()

api_key = email_config.api_key
from_email = email_config.from_email
```

## Environment Variables (Still Required)

These must be set in `.env` file for database initialization:

```
MAILERSEND_API_TOKEN=mlsn.<your-mailersend-api-token>
BREVO_API_KEY=xkeysib-<your-brevo-api-key>
```

After initialization, these are stored in the database and can be rotated through the admin panel.

## Real Data Only - Critical Rules

**NEVER** use mock or test data. The system enforces this:

1. **Email credentials** - Must be real API keys/tokens
2. **Brand configurations** - Must have valid from_email addresses
3. **API calls** - Will fail if credentials are invalid (expected)
4. **Error messages** - Provide clear feedback about credential issues

## Next Steps

1. ✅ Database architecture complete
2. ✅ Admin UI created
3. ✅ Admin API endpoints functional
4. 🔄 **TODO**: Update email analytics to read from database
5. 🔄 **TODO**: Add authentication/authorization to admin panel
6. 🔄 **TODO**: Create secrets management integration (Vault, AWS Secrets Manager)
7. 🔄 **TODO**: Add email provider verification/testing endpoints
8. 🔄 **TODO**: Create migration utilities for additional brands

## Troubleshooting

### Database Won't Initialize
```bash
# Check if database file exists
ls -la /Users/greglind/Projects/me/marketing/marketing_dashboard.db

# Reset database (DESTRUCTIVE!)
python -c "from dashboard.app import app; from dashboard.database import DatabaseManager; 
with app.app_context(): DatabaseManager(app).reset_db()"
```

### Admin Panel Not Loading
```bash
# Ensure templates directory exists
ls -la /Users/greglind/Projects/me/marketing/dashboard/templates/

# Check Flask logs
# Look for: "ERROR in app.before_request" in console output
```

### API Returns 500 Error
```bash
# Check app.py initialization logs
# Look for: "Database initialization error"
# Ensure BREVO_API_KEY and MAILERSEND_API_TOKEN are set in .env
```

## Support

For issues or questions:
1. Check logs: `tail -f /Users/greglind/Projects/me/marketing/logs/*.log`
2. Test database directly: `python dashboard/init_db.py`
3. Review project standards and current implementation notes in `devdocs/`
