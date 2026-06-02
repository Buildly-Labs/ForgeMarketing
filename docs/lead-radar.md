# Lead Radar (ForgeMarketing v1.3)

Lead Radar is a configurable human-in-the-loop lead research and prioritization module.

It supports multiple brands, users, regions, source strategies, scoring rules, and workflows.

## What Lead Radar Does

- Defines configurable regional profiles per brand.
- Tracks lead sources from approved/public/manual channels.
- Runs manual-assisted background research jobs to create candidate leads.
- Scores candidates and leads with transparent deterministic rules.
- Requires human review before candidate-to-lead conversion.
- Generates draft outreach only, never auto-sends messages.
- Creates optional manual follow-up tasks in the marketing calendar.
- Captures feedback to improve source quality tracking.

## What Lead Radar Does Not Automate

- Auto-sending cold emails.
- Auto-sending LinkedIn/Instagram DMs.
- Mass messaging prospects.
- Scraping private/restricted platform content.
- Bypassing platform terms.
- Fake personalization.

## Safety and Compliance Rules

- Respect `do_not_contact` at candidate and lead levels.
- Block draft generation and follow-up task creation when `do_not_contact` is set.
- Record source, owner, and compliance notes on every lead/source.
- Keep all outreach in draft/manual execution mode.
- Require human review before conversion and contact.

## Configuration Model

- RegionProfile: region-level targeting, pricing, tone, and ownership.
- LeadSource: configurable source strategy and frequency.
- ResearchJob: execution log for source runs.
- LeadCandidate: pre-lead records requiring review.
- ScoringRule: editable score rules by brand/region.
- Lead/LeadActivity/OutreachTemplate: core outreach planning records.
- LeadFeedback/SourcePerformance: quality and learning signals.
- LeadRadarSetting: brand-level module settings.

## Source Types

Traditional and non-traditional source types are supported:

- LinkedIn manual research
- Google search
- directories and event pages
- newsletters and RSS
- Product Hunt, Hacker News, Reddit
- GitHub
- YouTube and podcasts
- Instagram/LinkedIn manual post capture
- CSV import and manual entry

## Recommended Daily Workflow (Greg)

1. Open `/lead-radar` for queue and summary checks.
2. Review `/lead-radar/candidates` and approve/reject candidates.
3. Convert approved candidates to leads.
4. Review `/leads` and prioritize hot/high leads.
5. Generate outreach drafts and manually personalize/send via approved channels.
6. Update statuses and add follow-up activities.

## Recommended Daily Workflow (Gina)

1. Collect public/manual source inputs (URLs, notes, post text).
2. Add/update source records in `/lead-radar/sources`.
3. Run manual research jobs to create candidates.
4. Add review notes and suggested segment/region alignment.
5. Capture feedback (`good_fit`, `bad_source`, etc.) for learning.

## CSV Import

Endpoint: `POST /api/leads/import-csv`

Required data quality:

- `company_name` is required.
- At least one of name/linkedin/email/company_url is required.

Import behavior:

- deduplicates by linkedin/email/company+name
- auto-assigns region from region/country where possible
- defaults to `researched` status
- computes initial fit score
- never sends outreach

## Scoring and Priority

Default deterministic score model maps to:

- 80-100: hot
- 60-79: high
- 40-59: medium
- <40: low

Users can override score and priority manually.

## Draft Generation

Endpoint: `POST /api/leads/<id>/generate-draft`

- uses region profile, lead segment, and templates
- creates `LeadActivity` draft
- never sends any message
- displays mandatory warning for manual review/compliance

## Weekly Review Process

Use `/leads/dashboard` or `GET /api/leads/dashboard-summary` to review:

- leads added
- leads contacted
- replies
- calls booked
- proposals sent
- wins/losses
- best region
- best segment
- source performance

## Buildly Example Setup

Buildly defaults are included as seed data only:

- US West Coast
- US East Coast
- Southeast Asia
- Europe

Buildly templates, scoring rules, and source strategies are all editable and optional.

Other companies can create their own brands, regions, rules, offers, and workflows.
