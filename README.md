# ForgeMarketing

ForgeMarketing is a human-in-the-loop marketing operations tool for small teams.

It helps teams plan campaigns, draft content, organize assets, track manual tasks, and record performance across platforms without risky automation.

[![License: BSL-1.1→Apache-2.0](https://img.shields.io/badge/License-BSL%201.1-blue.svg)](LICENSE.md)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

## What ForgeMarketing Does

- Organizes work by brand/product and campaign.
- Tracks content from idea to draft, review, approval, scheduling, and posted state.
- Represents manual platform setup and posting steps as checklist tasks.
- Supports optional AI drafting assistance, always requiring human review.
- Tracks posted URLs and follow-up performance checks.
- Includes Lead Radar (Regional Lead Intelligence Engine) for configurable lead research, scoring, candidate review, draft outreach, and manual follow-up workflows.

## What ForgeMarketing Does Not Automate

- Social account creation.
- Platform verification.
- Mass following, auto-commenting, or DM spam.
- Any workflow that bypasses platform terms.
- Auto-publishing unapproved AI output.

## Human Approval Philosophy

ForgeMarketing helps teams plan and manage marketing content. It does not automatically create accounts, bypass platform rules, or post content without human approval. Account creation, platform verification, and final publishing should be completed by authorized humans following each platform's terms and policies.

## Quick Start

```bash
# Clone and navigate
git clone https://github.com/<your-org>/ForgeMarketing.git
cd ForgeMarketing

# Setup and start
./ops/startup.sh setup
./ops/startup.sh start
```

App URL: http://localhost:8002

## Core Workflow

1. Select or create a brand/product.
2. Select or create a campaign.
3. Add content ideas.
4. Create platform-specific drafts.
5. Attach assets.
6. Move drafts through review and approval.
7. Schedule externally or create manual posting tasks.
8. Save posted URLs.
9. Record performance snapshots.
10. Run weekly review and plan next actions.

## Intern-Friendly Docs

- [docs/intern-workflow.md](docs/intern-workflow.md)
- [docs/platform-account-setup.md](docs/platform-account-setup.md)
- [docs/content-calendar.md](docs/content-calendar.md)
- [docs/brand-voice.md](docs/brand-voice.md)
- [docs/forge-marketing-v1-2-plan.md](docs/forge-marketing-v1-2-plan.md)
- [docs/lead-radar.md](docs/lead-radar.md)
- [docs/regional-lead-engine.md](docs/regional-lead-engine.md)

Technical docs remain in [devdocs/README.md](devdocs/README.md).

## Setup Options

```bash
# Local
./ops/startup.sh setup
./ops/startup.sh start

# Custom port
./ops/startup.sh start --port 9000

# Docker
docker-compose -f ops/docker-compose.yml up -d
```

## Testing

```bash
# Smoke tests
python tests/smoke_check.py

# Pytest
pytest tests/smoke/ tests/crud/ -v
```

## Project Structure (High Level)

- [dashboard/](dashboard/) web UI and API endpoints
- [automation/](automation/) background and helper workflows
- [config/](config/) brand and system configuration
- [docs/](docs/) user-facing operational docs
- [devdocs/](devdocs/) technical architecture docs
- [tests/](tests/) smoke and unit tests

## License

- Until Nov 14, 2026: Business Source License 1.1 (BSL-1.1)
- After Nov 14, 2026: Apache License 2.0

See [LICENSE.md](LICENSE.md) for details.
