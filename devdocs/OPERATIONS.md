# Operations Guide

Deploy and manage ForgeMark in production environments.

## Docker Deployment

### Build Image

```bash
docker build -t buildly/forgemark:latest -f ops/Dockerfile .
```

### Run Container

```bash
docker run -d \
  --name forgemark \
  -p 5000:5000 \
  -e OLLAMA_HOST=ollama:11434 \
  -e FLASK_ENV=production \
  -v $(pwd)/data:/app/data \
  buildly/forgemark:latest
```

### Docker Compose

```bash
docker-compose -f ops/docker-compose.yml up -d
```

View logs:

```bash
docker logs -f forgemark
```

## Kubernetes Deployment

### Prerequisites

- kubectl configured and connected to cluster
- Helm 3+

### Install via Helm

```bash
helm repo add buildly https://charts.buildly.io
helm repo update

helm install forgemark buildly/forgemark \
  -n forgemark \
  --create-namespace \
  -f ops/helm/forgemark/values-example.yaml
```

### Upgrade

```bash
helm upgrade forgemark buildly/forgemark \
  -n forgemark \
  -f ops/helm/forgemark/values-example.yaml
```

### Health Check

```bash
kubectl get pods -n forgemark
kubectl logs -n forgemark deployment/forgemark
```

Access dashboard:

```bash
kubectl port-forward -n forgemark svc/forgemark 5000:5000
```

## GitHub Pages (Dashboard)

Static dashboard deployment to GitHub Pages:

```bash
cd dashboard
python build_static.py
```

Push generated files in `/docs` folder:

```bash
git add docs/
git commit -m "Update dashboard"
git push origin main
```

Enable Pages in repository settings:
- Set source to `main` branch, `/docs` folder
- Dashboard accessible at `https://buildlyio.github.io/marketing`

## Environment Variables

Required for production:

| Variable | Purpose |
|----------|---------|
| `FLASK_ENV` | Set to `production` |
| `SECRET_KEY` | Flask session key (generate: `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `OLLAMA_HOST` | Ollama service address |
| `DATABASE_URL` | PostgreSQL/MySQL connection string (optional) |

## Health Checks

All targets provide health endpoints:

```bash
curl http://localhost:5000/health
```

Expected response:

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2025-11-14T12:00:00Z"
}
```

## Monitoring & Logs

### Docker

```bash
docker logs forgemark
```

### Kubernetes

```bash
kubectl logs -n forgemark deployment/forgemark --tail=50 -f
```

### File-based

Logs written to `logs/` directory. Configure log retention in `config/logging.yaml`.

## Backup & Recovery

### Data Backup

```bash
# Backup databases
tar czf forgemark_backup_$(date +%s).tar.gz data/

# Restore
tar xzf forgemark_backup_*.tar.gz
```

### Configuration Backup

```bash
tar czf forgemark_config_$(date +%s).tar.gz config/
```

## Scaling

### Horizontal Scaling (Kubernetes)

```bash
kubectl scale deployment forgemark -n forgemark --replicas=3
```

### Performance Tuning

- Increase worker processes in `config/wsgi.yaml`
- Use external Postgres instead of SQLite for concurrency
- Enable caching for analytics dashboard

## Update Procedure

1. Pull latest version: `git pull origin main`
2. Run database migrations: `SKIP_STARTUP_DB_INIT=1 flask --app dashboard.app:app db upgrade`
3. Restart services: `docker restart forgemark` or `helm upgrade ...`
4. Verify health: `curl http://localhost:5000/health`

## Troubleshooting

### High Memory Usage
- Check for memory leaks in logs
- Reduce worker process count
- Enable swap if available

### Slow Campaign Processing
- Verify Ollama service is responsive
- Check database connection speed
- Review database indexes

### Email Delivery Issues
- Verify Brevo/email provider credentials
- Check firewall doesn't block SMTP ports
- Review email logs in `email_audit_logs/`

## Support

See **SUPPORT.md** for troubleshooting and support channels.
