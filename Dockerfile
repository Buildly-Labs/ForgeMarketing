FROM python:3.12-slim

ARG DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        nginx supervisor netcat-traditional poppler-utils \
        libsm6 libxext6 libxrender-dev postgresql-client \
        pkg-config default-libmysqlclient-dev build-essential \
        ffmpeg espeak-ng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── ForgeMarketing + Gateway deps ────────────────────────────
COPY requirements.txt /app/requirements-forge.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements-forge.txt bcrypt

# ── Producer deps ────────────────────────────────────────────
COPY Producer/requirements.txt /app/requirements-producer.txt
RUN pip install --no-cache-dir -r /app/requirements-producer.txt

# ── Copy application code ────────────────────────────────────
COPY . /app

# ── Collect Django static files ──────────────────────────────
RUN DJANGO_SETTINGS_MODULE=logic_service.settings.docker \
    RUNNING_IN_DOCKER=1 \
    python /app/Producer/manage.py collectstatic --no-input 2>/dev/null || true

# ── Nginx config ─────────────────────────────────────────────
COPY deploy/nginx.conf /etc/nginx/sites-available/default

# ── Supervisor config ────────────────────────────────────────
COPY deploy/supervisord.conf /etc/supervisor/conf.d/buildly.conf

# ── Data dir for SQLite ──────────────────────────────────────
RUN mkdir -p /app/data

EXPOSE 8080

CMD ["supervisord", "-n", "-c", "/etc/supervisor/conf.d/buildly.conf"]
