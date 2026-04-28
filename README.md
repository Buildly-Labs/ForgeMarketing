# ForgeMark - AI-Powered Marketing Automation

**One-command setup and deployment for multi-brand marketing automation.**

[![License: BSL-1.1→Apache-2.0](https://img.shields.io/badge/License-BSL%201.1-blue.svg)](LICENSE.md)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](ops/Dockerfile)

## 📚 Documentation

**Multi-Tenant Architecture**: See [`devdocs/`](devdocs/README.md) for complete guides
- [Getting Started](devdocs/00_START_HERE.md)
- [Database Architecture](devdocs/01_DATABASE_ARCHITECTURE.md)
- [Multi-Tenant Guide](devdocs/02_MULTI_TENANT_GUIDE.md)
- [Admin Panel API](devdocs/03_ADMIN_PANEL_API.md)
- [Implementation Checklist](devdocs/04_IMPLEMENTATION_CHECKLIST.md)

## ⚡ Quick Start (30 seconds)

```bash
# Clone (include submodules like Producer)
git clone --recurse-submodules https://github.com/Buildly-Marketplace/ForgeMarketing.git
cd ForgeMarketing

# Setup (one-time)
./ops/startup.sh setup

# Start server
./ops/startup.sh start
```

The script will:
1. ✓ Verify Python 3.8+
2. ✓ Create/activate virtual environment
3. ✓ Install dependencies
4. ✓ Configure environment variables
5. ✓ Run smoke tests
6. ✓ Start server on **http://localhost:8002**

## 🎯 Key Features

- **🤖 AI Content Generation** — Ollama-powered content for all channels
- **📧 Email Marketing** — Brevo integration with tracking and automation
- **🌐 Social Publishing** — Multi-platform posting (Twitter, Mastodon, Bluesky)
- **🔍 Influencer Discovery** — Automated outreach and relationship management
- **📊 Analytics Dashboard** — Real-time metrics, campaign ROI, cross-brand reporting
- **🎨 Multi-Brand Management** — Unified control for Buildly, The Foundry, Open Build, Radical Therapy
- **🐳 Enterprise Ready** — Docker, Kubernetes (Helm), and GitHub Pages support

## 📋 Setup Options

### Option 1: Local Development (Recommended for first-time)
```bash
./ops/startup.sh setup
./ops/startup.sh start
```

### Option 2: Custom Port
```bash
./ops/startup.sh start --port 9000
```

### Option 3: Fresh Installation
```bash
./ops/startup.sh setup --clean
./ops/startup.sh start
```

### Option 4: Docker
```bash
# Initialise submodules and build the image
./build.sh

# Start services
docker compose up -d
```

### Option 5: Kubernetes/Helm
```bash
helm install forgemark ops/helm/forgemark/ -n forgemark --create-namespace
```

## 🧪 Testing

### Smoke Tests (No pytest needed)
```bash
python tests/smoke_check.py
```

### pytest Tests
```bash
pip install pytest
pytest tests/smoke/ tests/crud/ -v
```

## 🛠️ File Organization

```
ForgeMarketing/
├── build.sh                     Submodule init + Docker build
├── Producer/                    Git submodule — Podcast Studio (Django)
├── ops/                         ✓ Deployment & setup
│   ├── startup.sh               Main setup/start/stop/restart script ⭐
│   ├── Dockerfile               Docker image
│   ├── docker-compose.yml       Multi-service stack
│   └── helm/forgemark/          Kubernetes charts
├── devdocs/                     ✓ Complete documentation
│   ├── SETUP.md                 Installation guide
│   ├── OPERATIONS.md            Deployment guide
│   ├── REFERENCE.md             API reference
│   └── ...
├── tests/                       ✓ All tests organized here
│   ├── smoke_check.py           Standalone smoke tests
│   ├── smoke/                   Pytest smoke tests
│   ├── crud/                    CRUD tests
│   └── [35+ utilities/setup/debug scripts]
├── automation/                  Core automation engines
├── config/                      Configuration files
├── dashboard/                   Web dashboard
├── templates/                   Email templates
├── data/                        Generated data
├── BUILDLY.yaml                 Marketplace metadata
├── LICENSE.md                   BSL-1.1 → Apache-2.0
├── SUPPORT.md                   Support scope
└── README.md                    This file
```

## 🔧 Environment Setup

The setup script handles this automatically, but manually:

```bash
cp .env.example .env
```

**Key variables:**
- `FLASK_ENV` - development or production
- `OLLAMA_HOST` - localhost:11434 (or remote)
- `DATABASE_URL` - PostgreSQL/MySQL (optional)
- `BREVO_API_KEY` - Email service
- `GOOGLE_ADS_CLIENT_ID` - Google Ads

## 📦 Requirements

- **Python 3.8+** (check: `python3 --version`)
- **Ollama** (for AI content generation) — optional but recommended
- **Docker** (optional, for containerized deployment)
- **Git** (for version control)

## 🚀 Common Commands

```bash
# Setup (one-time)
./ops/startup.sh setup

# Start server (default port 8002)
./ops/startup.sh start

# Start with custom port
./ops/startup.sh start --port 9000

# Stop server
./ops/startup.sh stop

# Restart server
./ops/startup.sh restart

# Fresh installation
./ops/startup.sh setup --clean

# Run smoke tests
python tests/smoke_check.py

# Start with Docker
docker-compose -f ops/docker-compose.yml up -d

# View deployment options
cat ops/README.md
```

## 🗄️ Database Migrations (Marketing Dashboard)

The Flask marketing dashboard now uses Alembic via Flask-Migrate.

Migrations run automatically in:
- `./ops/startup.sh setup`
- `./ops/startup.sh start`
- Docker/supervisor startup for the `marketing` service

```bash
# Create a migration from model changes
SKIP_STARTUP_DB_INIT=1 flask --app dashboard.app:app db migrate -m "describe change"

# Apply migrations
SKIP_STARTUP_DB_INIT=1 flask --app dashboard.app:app db upgrade

# Mark an existing pre-migration database as current baseline
SKIP_STARTUP_DB_INIT=1 flask --app dashboard.app:app db stamp head
```

Use `db stamp head` once for already-populated legacy databases before switching to `db upgrade`.

## 🐛 Troubleshooting

**Port already in use:**
```bash
./ops/startup.sh start --port 9000
```

**Python not found:**
Install Python 3.8+: https://python.org

**Ollama not responding:**
```bash
# In another terminal:
ollama serve

# Optional: Pull a model
ollama pull mistral
```

**Virtual environment issues:**
```bash
./ops/startup.sh setup --clean
```

**View server logs:**
```bash
tail -f ops/server.log
```

See **[SUPPORT.md](SUPPORT.md)** for more help.

## 📄 License

- **Until Nov 14, 2026:** Business Source License 1.1 (BSL-1.1)
- **After Nov 14, 2026:** Apache License 2.0

See [LICENSE.md](LICENSE.md) for details.

## 🤝 Support

- **Community:** [GitHub Issues](https://github.com/Buildly-Marketplace/ForgeMarketing/issues)
- **Discord:** [Buildly Community](https://discord.gg/buildly)
- **Documentation:** See [SUPPORT.md](SUPPORT.md)

## 🎓 Next Steps

1. **Run setup:** `./ops/startup.sh setup`
2. **Start server:** `./ops/startup.sh start`
3. **Access dashboard:** Open http://localhost:8002
4. **Read docs:** Start with [devdocs/SETUP.md](devdocs/SETUP.md)
4. **Run tests:** `python tests/smoke_check.py`
5. **Deploy:** See [devdocs/OPERATIONS.md](devdocs/OPERATIONS.md)

---

**Ready to scale multi-brand marketing with AI?** Let's go! 🚀
