# ForgeMarketing v1.2 Practical Plan

## Audit Summary (Current State)
- The repository already includes multi-brand structures, campaign/task APIs, and calendar-style UI in [dashboard/marketing_calendar_api.py](dashboard/marketing_calendar_api.py), [dashboard/marketing_calendar_models.py](dashboard/marketing_calendar_models.py), and [dashboard/templates/content_calendar.html](dashboard/templates/content_calendar.html).
- The dashboard UI has useful pages for campaigns, analytics, reports, and content operations, but several views still read as automation-first rather than intern workflow-first.
- Active files still contain product-specific references and defaults that make the project feel tied to a single organization.
- Existing model coverage is good for campaigns/tasks/templates, but missing some explicit workflow entities (content ideas, social post drafts, manual tasks, assets, performance snapshots) needed for a human-in-the-loop command-center flow.

## Disconnected Areas
- Hard-coded brand references in active UI/content make onboarding generic users difficult.
- Documentation is mostly technical and not intern workflow-oriented.
- Status flow in several places is inconsistent (task statuses vs draft/review/approved/scheduled/posted workflow).
- Manual steps (platform setup, approval, manual posting, analytics checks) are not consistently represented as explicit checklist tasks.

## Proposed Minimal Changes
- Keep current architecture and routes; avoid large refactors.
- Add lightweight workflow models for core concepts while preserving existing task/campaign structures.
- Add intern-focused operational docs and checklist templates.
- Update UI copy and key templates to emphasize human approval and manual platform responsibilities.
- Replace active hard-coded brand examples with neutral defaults and an optional Washoku fixture.

## Files Likely To Change
- [README.md](README.md)
- [docs/README.md](docs/README.md)
- [docs/intern-workflow.md](docs/intern-workflow.md)
- [docs/platform-account-setup.md](docs/platform-account-setup.md)
- [docs/content-calendar.md](docs/content-calendar.md)
- [docs/brand-voice.md](docs/brand-voice.md)
- [dashboard/marketing_calendar_models.py](dashboard/marketing_calendar_models.py)
- [dashboard/templates/dashboard.html](dashboard/templates/dashboard.html)
- [dashboard/templates/marketing_calendar.html](dashboard/templates/marketing_calendar.html)
- [dashboard/templates/base.html](dashboard/templates/base.html)
- [scripts/seed_database.py](scripts/seed_database.py)
- [examples/washoku_seed_data.json](examples/washoku_seed_data.json)

## Data Model Additions Needed (Minimal)
- ContentPillar
- ContentIdea
- SocialPostDraft
- ManualTask
- Asset
- PerformanceSnapshot
- Optional enum updates for review and approval states

## Risky Changes To Avoid
- No large route reorganization in [dashboard/app.py](dashboard/app.py).
- No breaking migration strategy; only additive model changes compatible with db.create_all.
- No automated account creation or risky platform automation features.
- No changes that alter existing outreach/email integrations unless required for neutral naming/copy.
