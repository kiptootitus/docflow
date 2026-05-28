###############################################################
# DocFlow — Outputs
###############################################################

output "alb_dns_name" {
  description = "ALB DNS — point your domain CNAME here if not using Route53"
  value       = aws_lb.docflow.dns_name
}

output "cloudfront_domain" {
  description = "CloudFront CDN domain for static/media files"
  value       = aws_cloudfront_distribution.docflow.domain_name
}

output "ecr_api_url" {
  description = "ECR URL for the Django API image"
  value       = aws_ecr_repository.docflow_api.repository_url
}

output "ecr_celery_url" {
  description = "ECR URL for the Celery image"
  value       = aws_ecr_repository.docflow_celery.repository_url
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = aws_db_instance.docflow.address
  sensitive   = true
}

output "redis_endpoint" {
  description = "ElastiCache Redis primary endpoint"
  value       = aws_elasticache_replication_group.docflow.primary_endpoint_address
  sensitive   = true
}

output "media_bucket" {
  value = aws_s3_bucket.media.bucket
}

output "static_bucket" {
  value = aws_s3_bucket.static.bucket
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.docflow.name
}
