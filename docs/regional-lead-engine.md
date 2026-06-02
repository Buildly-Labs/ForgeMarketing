# Regional Lead Engine (v1.3)

Regional Lead Engine is now productized as Lead Radar.

Use this page as a quick migration map from the original regional lead plan to the configurable multi-brand implementation.

## Included Core Capabilities

- region profiles and ownership
- lead CRUD and lead activities
- outreach template management
- CSV import with validation and dedupe
- deterministic scoring and priority mapping
- draft generation with human-review warning
- dashboard summary metrics by region/status/owner/priority
- task integration for next actions
- candidate review and conversion workflow
- feedback capture and source performance tracking

## Key Architecture Notes

- Flask + SQLAlchemy incremental extension
- no major framework refactor
- table creation via existing initialization flow (`db.create_all`)
- Buildly setup is seed data, not hardcoded behavior

## Safety Guardrails

- no auto-email sending
- no auto-DM behavior
- no private scraping
- no bypass of platform terms
- enforce do-not-contact workflow

## Startup and Setup

- `./ops/startup.sh setup`
- `./ops/startup.sh start`

These continue to work while creating the new Lead Radar tables via normal app/database initialization.
