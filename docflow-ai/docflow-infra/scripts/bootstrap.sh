#!/usr/bin/env bash
###############################################################
# DocFlow — Bootstrap Script
# Run ONCE before `terraform init` to create S3 state bucket
# and DynamoDB lock table.
###############################################################
set -euo pipefail

AWS_REGION="us-east-1"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
STATE_BUCKET="docflow-terraform-state"
LOCK_TABLE="docflow-terraform-locks"

log() { echo -e "\033[1;36m▶ $*\033[0m"; }
ok()  { echo -e "\033[1;32m✔ $*\033[0m"; }

#────────────────────────────────────────────────────────────
# 1. S3 bucket for Terraform state
#────────────────────────────────────────────────────────────
log "Creating Terraform state bucket: $STATE_BUCKET"
if aws s3api head-bucket --bucket "$STATE_BUCKET" 2>/dev/null; then
  ok "Bucket already exists"
else
  aws s3api create-bucket \
    --bucket "$STATE_BUCKET" \
    --region "$AWS_REGION"

  aws s3api put-bucket-versioning \
    --bucket "$STATE_BUCKET" \
    --versioning-configuration Status=Enabled

  aws s3api put-bucket-encryption \
    --bucket "$STATE_BUCKET" \
    --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

  aws s3api put-public-access-block \
    --bucket "$STATE_BUCKET" \
    --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

  ok "State bucket created and secured"
fi

#────────────────────────────────────────────────────────────
# 2. DynamoDB table for state locking
#────────────────────────────────────────────────────────────
log "Creating DynamoDB lock table: $LOCK_TABLE"
if aws dynamodb describe-table --table-name "$LOCK_TABLE" --region "$AWS_REGION" 2>/dev/null; then
  ok "DynamoDB table already exists"
else
  aws dynamodb create-table \
    --table-name "$LOCK_TABLE" \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region "$AWS_REGION"
  ok "DynamoDB lock table created"
fi

#────────────────────────────────────────────────────────────
# 3. Request ACM Certificate (HTTPS)
#────────────────────────────────────────────────────────────
log "Requesting ACM certificate..."
echo ""
echo "  You need an SSL certificate. Run this command:"
echo ""
echo "  aws acm request-certificate \\"
echo "    --domain-name 'api.docflow.com' \\"
echo "    --subject-alternative-names '*.docflow.com' \\"
echo "    --validation-method DNS \\"
echo "    --region us-east-1"
echo ""
echo "  Then add the DNS CNAME record shown in ACM console,"
echo "  wait for Status = Issued, then paste the ARN into terraform.tfvars"
echo ""

#────────────────────────────────────────────────────────────
# 4. Done
#────────────────────────────────────────────────────────────
ok "Bootstrap complete! Account: $AWS_ACCOUNT_ID, Region: $AWS_REGION"
echo ""
echo "Next steps:"
echo "  1. Copy terraform.tfvars.example → terraform.tfvars"
echo "  2. Fill in acm_certificate_arn and route53_zone_id"
echo "  3. cd terraform && terraform init"
echo "  4. terraform plan"
echo "  5. terraform apply"
echo "  6. cd .. && ./scripts/deploy.sh all"
