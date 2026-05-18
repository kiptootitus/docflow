#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────
# DocFlow AI — Bootstrap Script
# Run this once after cloning to set up the project.
# ──────────────────────────────────────────────────────────────────────────
set -e

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║         DocFlow AI — Bootstrap               ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# 1. Copy env file
if [ ! -f .env ]; then
  cp .env.example .env
  echo "✅  Created .env from .env.example"
  echo "⚠️   Please edit .env and fill in your API keys before continuing."
  echo ""
fi

# 2. Build & start containers
echo "🐳  Building Docker containers…"
docker compose build

echo ""
echo "🚀  Starting services (db + redis first)…"
docker compose up -d db redis

echo ""
echo "⏳  Waiting for database to be ready…"
sleep 5

# 3. Run migrations
echo ""
echo "🗄️   Running Django migrations…"
docker compose run --rm backend python manage.py migrate --settings=docflow.settings.production

# 4. Create superuser
echo ""
echo "👤  Creating Django superuser…"
docker compose run --rm backend python manage.py createsuperuser --settings=docflow.settings.production

# 5. Collect static
echo ""
echo "📦  Collecting static files…"
docker compose run --rm backend python manage.py collectstatic --noinput --settings=docflow.settings.production

# 6. Start all services
echo ""
echo "🟢  Starting all services…"
docker compose up -d

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  DocFlow AI is running!                                  ║"
echo "║                                                          ║"
echo "║  Web App      →  http://localhost:3000                   ║"
echo "║  API          →  http://localhost:8000/api/v1/           ║"
echo "║  API Docs     →  http://localhost:8000/api/docs/         ║"
echo "║  Django Admin →  http://localhost:8000/admin/            ║"
echo "║  Celery Flower→  http://localhost:5555                   ║"
echo "║  Nginx        →  http://localhost:80                     ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
