###############################################################
# DocFlow — Production AWS Infrastructure
# Author : Titus Tech Services
# Stack  : ALB → ECS Fargate → RDS PostgreSQL → ElastiCache Redis
###############################################################

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }

  # Remote state — create this S3 bucket manually once before `terraform init`
  backend "s3" {
    bucket         = "docflow-terraform-state"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "docflow-terraform-locks"
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project     = "DocFlow"
      Environment = var.environment
      ManagedBy   = "Terraform"
      Owner       = "TitusTechServices"
    }
  }
}

###############################################################
# DATA SOURCES
###############################################################
data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}

###############################################################
# VPC
###############################################################
resource "aws_vpc" "docflow" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = { Name = "docflow-vpc-${var.environment}" }
}

# Internet Gateway
resource "aws_internet_gateway" "docflow" {
  vpc_id = aws_vpc.docflow.id
  tags   = { Name = "docflow-igw" }
}

# Public Subnets (ALB lives here)
resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.docflow.id
  cidr_block              = cidrsubnet("10.0.0.0/16", 8, count.index)
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true
  tags                    = { Name = "docflow-public-${count.index + 1}" }
}

# Private Subnets (ECS tasks, RDS, Redis)
resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.docflow.id
  cidr_block        = cidrsubnet("10.0.0.0/16", 8, count.index + 10)
  availability_zone = data.aws_availability_zones.available.names[count.index]
  tags              = { Name = "docflow-private-${count.index + 1}" }
}

# NAT Gateway (private subnets → internet)
resource "aws_eip" "nat" {
  domain = "vpc"
  tags   = { Name = "docflow-nat-eip" }
}

resource "aws_nat_gateway" "docflow" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id
  tags          = { Name = "docflow-nat" }
  depends_on    = [aws_internet_gateway.docflow]
}

# Route Tables
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.docflow.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.docflow.id
  }
  tags = { Name = "docflow-rt-public" }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.docflow.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.docflow.id
  }
  tags = { Name = "docflow-rt-private" }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

###############################################################
# SECURITY GROUPS
###############################################################
resource "aws_security_group" "alb" {
  name        = "docflow-alb-sg"
  description = "Allow HTTP/HTTPS from anywhere"
  vpc_id      = aws_vpc.docflow.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "docflow-alb-sg" }
}

resource "aws_security_group" "ecs" {
  name        = "docflow-ecs-sg"
  description = "Allow traffic from ALB only"
  vpc_id      = aws_vpc.docflow.id

  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "docflow-ecs-sg" }
}

resource "aws_security_group" "rds" {
  name        = "docflow-rds-sg"
  description = "Allow PostgreSQL from ECS only"
  vpc_id      = aws_vpc.docflow.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }
  tags = { Name = "docflow-rds-sg" }
}

resource "aws_security_group" "redis" {
  name        = "docflow-redis-sg"
  description = "Allow Redis from ECS only"
  vpc_id      = aws_vpc.docflow.id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }
  tags = { Name = "docflow-redis-sg" }
}

###############################################################
# RDS POSTGRESQL (Multi-AZ)
###############################################################
resource "aws_db_subnet_group" "docflow" {
  name       = "docflow-db-subnet-group"
  subnet_ids = aws_subnet.private[*].id
  tags       = { Name = "docflow-db-subnet-group" }
}

resource "random_password" "db_password" {
  length  = 32
  special = false
}

resource "aws_secretsmanager_secret" "db_password" {
  name                    = "docflow/${var.environment}/db-password"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id     = aws_secretsmanager_secret.db_password.id
  secret_string = random_password.db_password.result
}

resource "aws_db_instance" "docflow" {
  identifier              = "docflow-postgres-${var.environment}"
  engine                  = "postgres"
  engine_version          = "16.2"
  instance_class          = var.db_instance_class
  allocated_storage       = 20
  max_allocated_storage   = 100
  storage_type            = "gp3"
  storage_encrypted       = true
  db_name                 = "docflow"
  username                = "docflow_admin"
  password                = random_password.db_password.result
  db_subnet_group_name    = aws_db_subnet_group.docflow.name
  vpc_security_group_ids  = [aws_security_group.rds.id]
  multi_az                = var.environment == "prod" ? true : false
  publicly_accessible     = false
  skip_final_snapshot     = var.environment != "prod"
  final_snapshot_identifier = var.environment == "prod" ? "docflow-final-snapshot" : null
  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "Mon:04:00-Mon:05:00"
  deletion_protection     = var.environment == "prod" ? true : false
  performance_insights_enabled = true

  tags = { Name = "docflow-postgres" }
}

###############################################################
# ELASTICACHE REDIS (Celery broker + Django cache)
###############################################################
resource "aws_elasticache_subnet_group" "docflow" {
  name       = "docflow-redis-subnet-group"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_elasticache_replication_group" "docflow" {
  replication_group_id = "docflow-redis-${var.environment}"
  description          = "DocFlow Redis cluster"
  node_type            = var.redis_node_type
  num_cache_clusters   = var.environment == "prod" ? 2 : 1
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.docflow.name
  security_group_ids   = [aws_security_group.redis.id]
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  automatic_failover_enabled = var.environment == "prod" ? true : false

  tags = { Name = "docflow-redis" }
}

###############################################################
# S3 — Media & Static Files
###############################################################
resource "aws_s3_bucket" "media" {
  bucket = "docflow-media-${var.environment}-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_versioning" "media" {
  bucket = aws_s3_bucket.media.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "media" {
  bucket = aws_s3_bucket.media.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_public_access_block" "media" {
  bucket                  = aws_s3_bucket.media.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket" "static" {
  bucket = "docflow-static-${var.environment}-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "static" {
  bucket                  = aws_s3_bucket.static.id
  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "static" {
  bucket = aws_s3_bucket.static.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = "*"
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.static.arn}/*"
    }]
  })
}

###############################################################
# CloudFront — CDN for media & static
###############################################################
resource "aws_cloudfront_origin_access_control" "media" {
  name                              = "docflow-media-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "docflow" {
  enabled             = true
  default_root_object = "index.html"
  price_class         = "PriceClass_100"
  comment             = "DocFlow CDN"

  origin {
    domain_name              = aws_s3_bucket.static.bucket_regional_domain_name
    origin_id                = "static-s3"
    origin_access_control_id = aws_cloudfront_origin_access_control.media.id
  }

  origin {
    domain_name              = aws_s3_bucket.media.bucket_regional_domain_name
    origin_id                = "media-s3"
    origin_access_control_id = aws_cloudfront_origin_access_control.media.id
  }

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "static-s3"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    forwarded_values {
      query_string = false
      cookies { forward = "none" }
    }

    min_ttl     = 0
    default_ttl = 86400
    max_ttl     = 31536000
  }

  ordered_cache_behavior {
    path_pattern           = "/media/*"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "media-s3"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    forwarded_values {
      query_string = false
      cookies { forward = "none" }
    }
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = { Name = "docflow-cdn" }
}

###############################################################
# ECR — Docker Image Registry
###############################################################
resource "aws_ecr_repository" "docflow_api" {
  name                 = "docflow/api"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_repository" "docflow_celery" {
  name                 = "docflow/celery"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.docflow_api.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 10 }
      action       = { type = "expire" }
    }]
  })
}

###############################################################
# ECS CLUSTER
###############################################################
resource "aws_ecs_cluster" "docflow" {
  name = "docflow-cluster-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_cluster_capacity_providers" "docflow" {
  cluster_name       = aws_ecs_cluster.docflow.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    base              = 1
    weight            = 70
    capacity_provider = "FARGATE"
  }
  default_capacity_provider_strategy {
    weight            = 30
    capacity_provider = "FARGATE_SPOT"
  }
}

###############################################################
# IAM — ECS Task Role
###############################################################
resource "aws_iam_role" "ecs_task_execution" {
  name = "docflow-ecs-task-execution-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "ecs_task" {
  name = "docflow-ecs-task-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "ecs_task_s3" {
  name = "docflow-ecs-s3-access"
  role = aws_iam_role.ecs_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.media.arn,
          "${aws_s3_bucket.media.arn}/*",
          aws_s3_bucket.static.arn,
          "${aws_s3_bucket.static.arn}/*",
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = [aws_secretsmanager_secret.db_password.arn]
      }
    ]
  })
}

###############################################################
# CLOUDWATCH LOG GROUPS
###############################################################
resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/docflow-api"
  retention_in_days = 30
}

resource "aws_cloudwatch_log_group" "celery" {
  name              = "/ecs/docflow-celery"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "celery_beat" {
  name              = "/ecs/docflow-celery-beat"
  retention_in_days = 14
}

###############################################################
# ECS TASK DEFINITION — Django API
###############################################################
resource "aws_ecs_task_definition" "api" {
  family                   = "docflow-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "docflow-api"
    image     = "${aws_ecr_repository.docflow_api.repository_url}:latest"
    essential = true
    portMappings = [{ containerPort = 8000, protocol = "tcp" }]

    environment = [
      { name = "DJANGO_SETTINGS_MODULE", value = "docflow.settings.production" },
      { name = "ALLOWED_HOSTS",          value = var.domain_name },
      { name = "DB_HOST",                value = aws_db_instance.docflow.address },
      { name = "DB_NAME",                value = "docflow" },
      { name = "DB_USER",                value = "docflow_admin" },
      { name = "DB_PORT",                value = "5432" },
      { name = "REDIS_URL",              value = "rediss://${aws_elasticache_replication_group.docflow.primary_endpoint_address}:6379/0" },
      { name = "AWS_STORAGE_BUCKET_NAME", value = aws_s3_bucket.media.bucket },
      { name = "AWS_S3_REGION_NAME",     value = var.aws_region },
      { name = "STATIC_BUCKET",         value = aws_s3_bucket.static.bucket },
      { name = "CLOUDFRONT_DOMAIN",     value = aws_cloudfront_distribution.docflow.domain_name },
    ]

    secrets = [
      { name = "DB_PASSWORD", valueFrom = aws_secretsmanager_secret.db_password.arn }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.api.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "api"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8000/health/ || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }
  }])
}

###############################################################
# ECS TASK DEFINITION — Celery Worker
###############################################################
resource "aws_ecs_task_definition" "celery" {
  family                   = "docflow-celery"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "docflow-celery"
    image     = "${aws_ecr_repository.docflow_celery.repository_url}:latest"
    essential = true
    command   = ["celery", "-A", "docflow", "worker", "-l", "info", "--concurrency=4"]

    environment = [
      { name = "DJANGO_SETTINGS_MODULE", value = "docflow.settings.production" },
      { name = "DB_HOST",                value = aws_db_instance.docflow.address },
      { name = "DB_NAME",                value = "docflow" },
      { name = "DB_USER",                value = "docflow_admin" },
      { name = "REDIS_URL",              value = "rediss://${aws_elasticache_replication_group.docflow.primary_endpoint_address}:6379/0" },
    ]

    secrets = [
      { name = "DB_PASSWORD", valueFrom = aws_secretsmanager_secret.db_password.arn }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.celery.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "celery"
      }
    }
  }])
}

###############################################################
# ECS TASK DEFINITION — Celery Beat
###############################################################
resource "aws_ecs_task_definition" "celery_beat" {
  family                   = "docflow-celery-beat"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "docflow-beat"
    image     = "${aws_ecr_repository.docflow_celery.repository_url}:latest"
    essential = true
    command   = ["celery", "-A", "docflow", "beat", "-l", "info", "--scheduler", "django_celery_beat.schedulers:DatabaseScheduler"]

    environment = [
      { name = "DJANGO_SETTINGS_MODULE", value = "docflow.settings.production" },
      { name = "DB_HOST",                value = aws_db_instance.docflow.address },
      { name = "DB_NAME",                value = "docflow" },
      { name = "DB_USER",                value = "docflow_admin" },
      { name = "REDIS_URL",              value = "rediss://${aws_elasticache_replication_group.docflow.primary_endpoint_address}:6379/0" },
    ]

    secrets = [
      { name = "DB_PASSWORD", valueFrom = aws_secretsmanager_secret.db_password.arn }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.celery_beat.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "beat"
      }
    }
  }])
}

###############################################################
# APPLICATION LOAD BALANCER
###############################################################
resource "aws_lb" "docflow" {
  name               = "docflow-alb-${var.environment}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id
  enable_deletion_protection = var.environment == "prod" ? true : false

  access_logs {
    bucket  = aws_s3_bucket.media.bucket
    prefix  = "alb-logs"
    enabled = true
  }

  tags = { Name = "docflow-alb" }
}

resource "aws_lb_target_group" "api" {
  name        = "docflow-api-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.docflow.id
  target_type = "ip"

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    path                = "/health/"
    matcher             = "200"
  }

  deregistration_delay = 30
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.docflow.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.docflow.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.acm_certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

###############################################################
# ECS SERVICES
###############################################################
resource "aws_ecs_service" "api" {
  name            = "docflow-api"
  cluster         = aws_ecs_cluster.docflow.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "docflow-api"
    container_port   = 8000
  }

  deployment_configuration {
    minimum_healthy_percent = 100
    maximum_percent         = 200

    deployment_circuit_breaker {
      enable   = true
      rollback = true
    }
  }

  enable_execute_command = true   # ECS Exec for live debugging

  depends_on = [aws_lb_listener.https]
  lifecycle { ignore_changes = [desired_count] }
}

resource "aws_ecs_service" "celery" {
  name            = "docflow-celery"
  cluster         = aws_ecs_cluster.docflow.id
  task_definition = aws_ecs_task_definition.celery.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  enable_execute_command = true
}

resource "aws_ecs_service" "celery_beat" {
  name            = "docflow-celery-beat"
  cluster         = aws_ecs_cluster.docflow.id
  task_definition = aws_ecs_task_definition.celery_beat.arn
  desired_count   = 1   # Always exactly 1 — Beat must be singleton
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }
}

###############################################################
# AUTO SCALING — API Service
###############################################################
resource "aws_appautoscaling_target" "api" {
  max_capacity       = 10
  min_capacity       = var.api_desired_count
  resource_id        = "service/${aws_ecs_cluster.docflow.name}/${aws_ecs_service.api.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "api_cpu" {
  name               = "docflow-api-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.api.resource_id
  scalable_dimension = aws_appautoscaling_target.api.scalable_dimension
  service_namespace  = aws_appautoscaling_target.api.service_namespace

  target_tracking_scaling_policy_configuration {
    target_value       = 70.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
  }
}

resource "aws_appautoscaling_policy" "api_memory" {
  name               = "docflow-api-memory-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.api.resource_id
  scalable_dimension = aws_appautoscaling_target.api.scalable_dimension
  service_namespace  = aws_appautoscaling_target.api.service_namespace

  target_tracking_scaling_policy_configuration {
    target_value       = 80.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageMemoryUtilization"
    }
  }
}

###############################################################
# WAF — Web Application Firewall
###############################################################
resource "aws_wafv2_web_acl" "docflow" {
  name  = "docflow-waf"
  scope = "REGIONAL"

  default_action { allow {} }

  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 1
    override_action { none {} }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "CommonRuleSet"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "RateLimitRule"
    priority = 2
    action { block {} }
    statement {
      rate_based_statement {
        limit              = 2000
        aggregate_key_type = "IP"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "RateLimit"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "docflow-waf"
    sampled_requests_enabled   = true
  }
}

resource "aws_wafv2_web_acl_association" "docflow" {
  resource_arn = aws_lb.docflow.arn
  web_acl_arn  = aws_wafv2_web_acl.docflow.arn
}

###############################################################
# ROUTE 53
###############################################################
data "aws_route53_zone" "docflow" {
  count = var.route53_zone_id != "" ? 1 : 0
  zone_id = var.route53_zone_id
}

resource "aws_route53_record" "api" {
  count   = var.route53_zone_id != "" ? 1 : 0
  zone_id = var.route53_zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = aws_lb.docflow.dns_name
    zone_id                = aws_lb.docflow.zone_id
    evaluate_target_health = true
  }
}
