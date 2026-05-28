# DocFlow — AWS Production Infrastructure

**Stack:** ALB → ECS Fargate → RDS PostgreSQL 16 → ElastiCache Redis → S3 + CloudFront + WAF

---

## Architecture Overview

```
Internet
   │
   ▼
CloudFront CDN ──────────────────── S3 (static + media)
   │
   ▼
WAF (rate limit + OWASP rules)
   │
   ▼
Application Load Balancer  (HTTPS 443, HTTP→HTTPS redirect)
   │        │
   ▼        ▼
ECS Task  ECS Task          ← auto-scales 2–10 replicas
(Django)  (Django)
   │
   ├── RDS PostgreSQL 16 (Multi-AZ, encrypted, automated backups)
   ├── ElastiCache Redis  (TLS, 2-node cluster)
   └── S3 Media Bucket    (private, CloudFront-served)

ECS Celery Worker  (async tasks)
ECS Celery Beat    (scheduled tasks, singleton)
```

---

## Prerequisites

| Tool | Version |
|------|---------|
| AWS CLI | ≥ 2.x, configured with `aws configure` |
| Terraform | ≥ 1.5 |
| Docker | ≥ 24 |
| Git | any |

---

## Step-by-Step Deployment

### Step 1 — Bootstrap (run once)

```bash
chmod +x scripts/bootstrap.sh
./scripts/bootstrap.sh
```

This creates:
- S3 bucket for Terraform remote state
- DynamoDB table for state locking
- Instructions to request your SSL certificate

---

### Step 2 — Request SSL Certificate

```bash
aws acm request-certificate \
  --domain-name "api.docflow.com" \
  --subject-alternative-names "*.docflow.com" \
  --validation-method DNS \
  --region us-east-1
```

1. Go to **AWS Console → Certificate Manager**
2. Click your certificate → **Create records in Route 53** (or add the CNAME manually)
3. Wait ~5 minutes for Status = **Issued**
4. Copy the certificate ARN

---

### Step 3 — Configure Variables

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:

```hcl
domain_name         = "api.docflow.com"      # your domain
acm_certificate_arn = "arn:aws:acm:..."      # from Step 2
route53_zone_id     = "ZXXXXXXXXX"           # your hosted zone
```

---

### Step 4 — Terraform Init & Apply

```bash
cd terraform

terraform init          # downloads providers, configures S3 backend
terraform plan          # preview what will be created (review carefully)
terraform apply         # type "yes" to confirm — takes ~10–15 minutes
```

After apply, note the outputs:
```
alb_dns_name      = "docflow-alb-prod-xxxx.us-east-1.elb.amazonaws.com"
cloudfront_domain = "dxxxxxxxxxx.cloudfront.net"
ecr_api_url       = "123456789.dkr.ecr.us-east-1.amazonaws.com/docflow/api"
ecr_celery_url    = "123456789.dkr.ecr.us-east-1.amazonaws.com/docflow/celery"
```

---

### Step 5 — Configure Your App

Copy `docker/settings_production.py` into your Django project:
```
docflow/settings/production.py
```

Add to `requirements.txt` if not already there:
```
gunicorn
uvicorn[standard]
boto3
django-storages[s3]
django-redis
psycopg2-binary
python-json-logger
dj-rest-auth[with_social]
```

Add health check URL to `docflow/urls.py`:
```python
from django.http import HttpResponse
urlpatterns = [
    ...
    path("health/", lambda r: HttpResponse("ok"), name="health"),
]
```

Copy `docker/Dockerfile.api` to your project root as `Dockerfile.api`.

---

### Step 6 — Set Django Secret Key in AWS Secrets Manager

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"

aws secretsmanager create-secret \
  --name "docflow/prod/django-secret-key" \
  --secret-string "YOUR_GENERATED_SECRET_KEY"
```

Add `DJANGO_SECRET_KEY` to the `secrets` section of the ECS task definition in `main.tf`, then re-apply.

---

### Step 7 — Deploy

```bash
# From your project root
chmod +x infra/scripts/deploy.sh

./infra/scripts/deploy.sh all    # builds images, runs migrations, deploys everything
./infra/scripts/deploy.sh api    # API only
./infra/scripts/deploy.sh celery # Celery only
```

---

## Accessing Your Site

### After Deploy

| What | URL/Command |
|------|-------------|
| **Live site** | `https://api.docflow.com` |
| **ALB direct** | `http://[alb_dns_name]` (use for testing before DNS) |
| **Health check** | `curl https://api.docflow.com/health/` → `ok` |

### Live Logs

```bash
# Tail API logs
aws logs tail /ecs/docflow-api --follow --region us-east-1

# Tail Celery logs
aws logs tail /ecs/docflow-celery --follow --region us-east-1
```

### Shell into Running Container (ECS Exec)

```bash
# Get a task ID
TASK=$(aws ecs list-tasks --cluster docflow-cluster-prod --service docflow-api \
  --query 'taskArns[0]' --output text | awk -F/ '{print $NF}')

# Open a bash shell
aws ecs execute-command \
  --cluster docflow-cluster-prod \
  --task $TASK \
  --container docflow-api \
  --command "/bin/bash" \
  --interactive
```

### Run Django Management Commands

```bash
# Example: createsuperuser
aws ecs run-task \
  --cluster docflow-cluster-prod \
  --task-definition docflow-api \
  --launch-type FARGATE \
  --overrides '{"containerOverrides":[{"name":"docflow-api","command":["python","manage.py","createsuperuser"]}]}'
```

---

## DNS Setup (if not using Route 53)

If your domain is on Cloudflare, Namecheap, etc.:

1. Get ALB DNS from Terraform output: `alb_dns_name`
2. Add a **CNAME** record:
   ```
   api.docflow.com  →  [alb_dns_name]
   ```
3. Or an **A record (ALIAS)** if your DNS provider supports it

---

## Cost Estimate (us-east-1)

| Service | Spec | ~Monthly (USD) |
|---------|------|----------------|
| ECS Fargate (2 tasks × 1vCPU/2GB) | Always on | ~$60 |
| RDS PostgreSQL db.t3.medium Multi-AZ | | ~$100 |
| ElastiCache cache.t3.micro (2 nodes) | | ~$30 |
| ALB | | ~$20 |
| NAT Gateway | | ~$35 |
| S3 + CloudFront | Low traffic | ~$5 |
| WAF | | ~$10 |
| **Total** | | **~$260/month** |

> **Cost tip:** Switch to `db.t3.small` and single-AZ for staging to cut to ~$80/month.

---

## Destroy (when needed)

```bash
cd terraform
terraform destroy   # destroys everything — be very careful in prod
```

---

## File Structure

```
docflow-infra/
├── terraform/
│   ├── main.tf                  # All AWS resources
│   ├── variables.tf             # Variable declarations
│   ├── outputs.tf               # Output values
│   └── terraform.tfvars.example # Copy → terraform.tfvars
├── scripts/
│   ├── bootstrap.sh             # Run once before terraform init
│   └── deploy.sh                # Build + deploy script
└── docker/
    ├── Dockerfile.api           # Production Django image
    └── settings_production.py  # Django production settings
```
