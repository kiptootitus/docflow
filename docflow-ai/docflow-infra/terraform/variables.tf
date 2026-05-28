###############################################################
# DocFlow — Terraform Variables
###############################################################

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (prod / staging)"
  type        = string
  default     = "prod"
}

variable "domain_name" {
  description = "Your domain e.g. api.docflow.com"
  type        = string
  default     = "api.docflow.com"
}

variable "acm_certificate_arn" {
  description = "ARN of ACM SSL certificate for your domain (must be in us-east-1 for CloudFront)"
  type        = string
}

variable "route53_zone_id" {
  description = "Route53 Hosted Zone ID (leave empty to skip DNS record creation)"
  type        = string
  default     = ""
}

# ---------- Compute ----------
variable "api_cpu" {
  description = "ECS task CPU units for API"
  type        = string
  default     = "1024"   # 1 vCPU
}

variable "api_memory" {
  description = "ECS task memory (MB) for API"
  type        = string
  default     = "2048"   # 2 GB
}

variable "api_desired_count" {
  description = "Initial number of API task replicas"
  type        = number
  default     = 2
}

# ---------- Database ----------
variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.medium"
}

# ---------- Redis ----------
variable "redis_node_type" {
  description = "ElastiCache node type"
  type        = string
  default     = "cache.t3.micro"
}
