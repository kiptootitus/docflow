#!/usr/bin/env bash
###############################################################
# DocFlow — Deploy Script
# Usage: ./deploy.sh [api|celery|all]  (default: all)
# Run from your project root where docker-compose.yml lives
###############################################################
set -euo pipefail

#────────────────────────────────────────────────────────────
# CONFIG — edit these once
#────────────────────────────────────────────────────────────
AWS_REGION="us-east-1"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_BASE="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
ECR_API="${ECR_BASE}/docflow/api"
ECR_CELERY="${ECR_BASE}/docflow/celery"
ECS_CLUSTER="docflow-cluster-prod"
ECS_SERVICE_API="docflow-api"
ECS_SERVICE_CELERY="docflow-celery"
ECS_SERVICE_BEAT="docflow-celery-beat"
STATIC_BUCKET="docflow-static-prod-${AWS_ACCOUNT_ID}"   # filled by Terraform output

TARGET=${1:-all}
GIT_SHA=$(git rev-parse --short HEAD)
IMAGE_TAG="${GIT_SHA}-$(date +%Y%m%d%H%M%S)"

log()  { echo -e "\033[1;36m▶ $*\033[0m"; }
ok()   { echo -e "\033[1;32m✔ $*\033[0m"; }
err()  { echo -e "\033[1;31m✘ $*\033[0m"; exit 1; }

#────────────────────────────────────────────────────────────
# 1. ECR Login
#────────────────────────────────────────────────────────────
log "Logging into ECR..."
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ECR_BASE"
ok "ECR login successful"

#────────────────────────────────────────────────────────────
# 2. Build & Push Images
#────────────────────────────────────────────────────────────
build_and_push_api() {
  log "Building API image (tag: $IMAGE_TAG)..."
  docker build \
    --target production \
    --build-arg BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --build-arg GIT_SHA="$GIT_SHA" \
    -t "${ECR_API}:${IMAGE_TAG}" \
    -t "${ECR_API}:latest" \
    -f Dockerfile.api .

  log "Pushing API image..."
  docker push "${ECR_API}:${IMAGE_TAG}"
  docker push "${ECR_API}:latest"
  ok "API image pushed → ${ECR_API}:${IMAGE_TAG}"
}

build_and_push_celery() {
  log "Building Celery image (tag: $IMAGE_TAG)..."
  docker build \
    --target production \
    -t "${ECR_CELERY}:${IMAGE_TAG}" \
    -t "${ECR_CELERY}:latest" \
    -f Dockerfile.celery .

  log "Pushing Celery image..."
  docker push "${ECR_CELERY}:${IMAGE_TAG}"
  docker push "${ECR_CELERY}:latest"
  ok "Celery image pushed → ${ECR_CELERY}:${IMAGE_TAG}"
}

#────────────────────────────────────────────────────────────
# 3. Collect Static → S3
#────────────────────────────────────────────────────────────
collect_static() {
  log "Collecting static files to S3..."
  docker run --rm \
    -e DJANGO_SETTINGS_MODULE=docflow.settings.production \
    -e AWS_DEFAULT_REGION="$AWS_REGION" \
    "${ECR_API}:${IMAGE_TAG}" \
    python manage.py collectstatic --noinput
  ok "Static files synced to s3://${STATIC_BUCKET}/static/"
}

#────────────────────────────────────────────────────────────
# 4. Run Migrations (one-off ECS task)
#────────────────────────────────────────────────────────────
run_migrations() {
  log "Running Django migrations via ECS one-off task..."
  TASK_DEF=$(aws ecs describe-task-definition \
    --task-definition docflow-api \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text)

  TASK_ARN=$(aws ecs run-task \
    --cluster "$ECS_CLUSTER" \
    --task-definition "$TASK_DEF" \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[$(aws ec2 describe-subnets --filters "Name=tag:Name,Values=docflow-private-*" --query 'Subnets[].SubnetId' --output text | tr '\t' ',')],securityGroups=[$(aws ec2 describe-security-groups --filters "Name=tag:Name,Values=docflow-ecs-sg" --query 'SecurityGroups[].GroupId' --output text)],assignPublicIp=DISABLED}" \
    --overrides '{"containerOverrides":[{"name":"docflow-api","command":["python","manage.py","migrate","--noinput"]}]}' \
    --query 'tasks[0].taskArn' \
    --output text)

  log "Migration task: $TASK_ARN"
  log "Waiting for migration to complete..."
  aws ecs wait tasks-stopped --cluster "$ECS_CLUSTER" --tasks "$TASK_ARN"

  EXIT_CODE=$(aws ecs describe-tasks \
    --cluster "$ECS_CLUSTER" \
    --tasks "$TASK_ARN" \
    --query 'tasks[0].containers[0].exitCode' \
    --output text)

  [ "$EXIT_CODE" == "0" ] && ok "Migrations completed" || err "Migration failed with exit code $EXIT_CODE"
}

#────────────────────────────────────────────────────────────
# 5. Update ECS Services (rolling deploy)
#────────────────────────────────────────────────────────────
deploy_api() {
  log "Deploying API service..."
  aws ecs update-service \
    --cluster "$ECS_CLUSTER" \
    --service "$ECS_SERVICE_API" \
    --force-new-deployment \
    --output table

  log "Waiting for API service to stabilize..."
  aws ecs wait services-stable \
    --cluster "$ECS_CLUSTER" \
    --services "$ECS_SERVICE_API"
  ok "API service deployed and stable"
}

deploy_celery() {
  log "Deploying Celery worker..."
  aws ecs update-service \
    --cluster "$ECS_CLUSTER" \
    --service "$ECS_SERVICE_CELERY" \
    --force-new-deployment \
    --output table

  log "Deploying Celery Beat..."
  aws ecs update-service \
    --cluster "$ECS_CLUSTER" \
    --service "$ECS_SERVICE_BEAT" \
    --force-new-deployment \
    --output table

  log "Waiting for Celery services to stabilize..."
  aws ecs wait services-stable \
    --cluster "$ECS_CLUSTER" \
    --services "$ECS_SERVICE_CELERY" "$ECS_SERVICE_BEAT"
  ok "Celery services deployed and stable"
}

#────────────────────────────────────────────────────────────
# MAIN
#────────────────────────────────────────────────────────────
case "$TARGET" in
  api)
    build_and_push_api
    collect_static
    run_migrations
    deploy_api
    ;;
  celery)
    build_and_push_celery
    deploy_celery
    ;;
  all)
    build_and_push_api
    build_and_push_celery
    collect_static
    run_migrations
    deploy_api
    deploy_celery
    ;;
  *)
    err "Unknown target: $TARGET. Use: api | celery | all"
    ;;
esac

echo ""
ok "🚀 DocFlow deploy complete! TAG=${IMAGE_TAG}"
echo ""
echo "  Site URL : https://api.docflow.com"
echo "  Logs     : aws logs tail /ecs/docflow-api --follow"
echo "  Shell    : aws ecs execute-command --cluster $ECS_CLUSTER --service $ECS_SERVICE_API --command /bin/bash --interactive"
