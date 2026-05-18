# DocFlow AI 🚀

**AI-powered invoice, contract, and document management — built with Django + React + Docker.**

---

## Architecture

```
docflow-ai/
├── backend/               Django 5 + DRF + Celery
│   ├── docflow/           Project settings & URLs
│   ├── apps/
│   │   ├── users/         Custom User model, JWT auth
│   │   ├── companies/     Company & Client models
│   │   ├── documents/     Invoices, Quotations, Contracts + PDF gen
│   │   ├── billing/       Stripe subscriptions & payment links
│   │   └── ai/            Claude AI contract review & doc generation
│   └── templates/         HTML → PDF (WeasyPrint) & email templates
├── web/                   React 19 + TypeScript + Tailwind CSS v4
│   └── src/
│       ├── pages/         Dashboard, Invoices, AI Review, etc.
│       ├── components/    Shared UI (layout, sidebar)
│       └── lib/           API client, auth store, utilities
├── nginx/                 Reverse proxy configuration
├── scripts/               Bootstrap & DB init scripts
└── docker-compose.yml     Full stack orchestration
```

## Docker Services

| Service          | Port  | Description                          |
|-----------------|-------|--------------------------------------|
| `db`            | 5432  | PostgreSQL 16                        |
| `redis`         | 6379  | Redis 7 (broker + cache)             |
| `backend`       | 8000  | Django + Gunicorn                    |
| `celery_worker` | —     | Async task processing                |
| `celery_beat`   | —     | Scheduled tasks (overdue reminders)  |
| `flower`        | 5555  | Celery monitoring dashboard          |
| `web`           | 3000  | React dev server                     |
| `nginx`         | 80    | Reverse proxy                        |

---

## Quick Start

### Prerequisites
- Docker Desktop 4.x+
- Docker Compose v2+

### 1. Clone & configure

```bash
git clone <your-repo>
cd docflow-ai
cp .env.example .env
# Edit .env — minimum required:
#   SECRET_KEY, ANTHROPIC_API_KEY, STRIPE keys
```

### 2. Bootstrap (first time only)

```bash
chmod +x scripts/bootstrap.sh
./scripts/bootstrap.sh
```

This will:
- Build all Docker images
- Run database migrations
- Create a Django superuser
- Collect static files
- Start all services

### 3. Access the app

| URL | Description |
|-----|-------------|
| http://localhost:3000 | React web app |
| http://localhost:8000/api/docs/ | Swagger API docs |
| http://localhost:8000/admin/ | Django admin |
| http://localhost:5555 | Celery Flower |

---

## Daily Development

```bash
# Start everything
docker compose up -d

# Stop everything
docker compose down

# View logs
docker compose logs -f backend
docker compose logs -f celery_worker

# Run Django shell
docker compose exec backend python manage.py shell

# Run migrations after model changes
docker compose exec backend python manage.py makemigrations
docker compose exec backend python manage.py migrate

# Run tests
docker compose exec backend pytest

# Run tests with coverage
docker compose exec backend pytest --cov=apps --cov-report=term-missing
```

---

## API Endpoints

### Auth
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/register/` | Create account |
| POST | `/api/v1/auth/login/` | Get JWT tokens |
| POST | `/api/v1/auth/token/refresh/` | Refresh access token |
| GET | `/api/v1/auth/me/` | Current user profile |
| POST | `/api/v1/auth/logout/` | Blacklist refresh token |

### Invoices
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/documents/invoices/` | List invoices |
| POST | `/api/v1/documents/invoices/` | Create invoice |
| GET | `/api/v1/documents/invoices/{id}/` | Get invoice |
| PATCH | `/api/v1/documents/invoices/{id}/` | Update invoice |
| DELETE | `/api/v1/documents/invoices/{id}/` | Delete invoice |
| POST | `/api/v1/documents/invoices/{id}/send_email/` | Email to client |
| POST | `/api/v1/documents/invoices/{id}/mark_paid/` | Mark as paid |
| POST | `/api/v1/documents/invoices/{id}/generate_pdf/` | Queue PDF generation |
| POST | `/api/v1/documents/invoices/{id}/duplicate/` | Duplicate invoice |

### AI
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/ai/review/` | Review contract PDF |
| GET | `/api/v1/ai/review/` | List reviews |
| POST | `/api/v1/ai/generate/` | Generate document |
| POST | `/api/v1/ai/generate/stream/` | Stream generation (SSE) |

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | ✅ | Django secret key (50+ chars) |
| `ANTHROPIC_API_KEY` | ✅ | Claude AI API key |
| `STRIPE_SECRET_KEY` | ✅ | Stripe payments |
| `STRIPE_WEBHOOK_SECRET` | ✅ | Stripe webhook verification |
| `POSTGRES_PASSWORD` | ✅ | Database password |
| `REDIS_PASSWORD` | ✅ | Redis password |
| `SENDGRID_API_KEY` | ⚡ | Email (optional in dev) |
| `AWS_ACCESS_KEY_ID` | ⚡ | S3 storage (uses local if absent) |
| `OPENAI_API_KEY` | ⚡ | GPT-4 fallback for AI |

---

## Features

- 📄 **Invoice Management** — Create, send, track, duplicate invoices with PDF export
- 📑 **Contract Management** — Draft, sign, track contracts
- 🤖 **AI Contract Review** — Upload PDF → Claude analyses risks, compliance, suggestions
- ✨ **AI Document Generation** — Generate NDA, service agreements, freelance contracts
- 💳 **Stripe Payments** — Subscriptions, payment links, webhooks
- 👥 **Client Portal** — Public invoice view & payment (no login required)
- 📧 **Email Automation** — Invoice sending, payment reminders via Celery
- 🔐 **JWT Auth** — Secure auth with refresh token rotation
- 📱 **Mobile Ready** — React Native app scaffold in `/mobile`

---

## Tech Stack

**Backend:** Python 3.12, Django 5, DRF, PostgreSQL 16, Redis 7, Celery 5, WeasyPrint, python-docx, Anthropic Claude, Stripe, SendGrid

**Frontend:** React 19, TypeScript, Vite, Tailwind CSS v4, TanStack Query, Zustand, react-hook-form, Zod

**Infrastructure:** Docker, Docker Compose, Nginx, Gunicorn, GitHub Actions

---

## Production Deployment

For production on AWS:

```bash
# 1. Update .env for production (real keys, DEBUG=False)
# 2. Use AWS RDS instead of local postgres
# 3. Push to AWS ECR:
docker compose -f docker-compose.yml build
docker tag docflow-backend:latest <account>.dkr.ecr.us-east-1.amazonaws.com/docflow-backend:latest
docker push <account>.dkr.ecr.us-east-1.amazonaws.com/docflow-backend:latest

# 4. Deploy React to Vercel:
cd web && vercel --prod
```

---

## License

MIT — Build something great! 🚀
