terraform {
    required_providers {
        aws = {
            source  = "hashicorp/aws"
                version = "~> 6.32.1"
        }
    }
}

provider "aws" {
    region = var.region
}

resource "aws_ecs_cluster" "main" {
  name = "${var.service-name}-cluster"

  setting {
    name = "containerInsights"
    value = "enabled"
  }
}

resource "aws_iam_role" "ecs_task_execution_role" {
    name = "${var.service-name}-task-execution-role"

    assume_role_policy = jsonencode({
        Version = "2012-10-17"
        Statement = [{
            Action = "sts:AssumeRole"
            Effect = "Allow"
            Principal = { Service = "ecs-tasks.amazonaws.com" }
        }]
    })
}

# Attach the standard AWS policy for ECS Task Execution
resource "aws_iam_role_policy_attachment" "ecs_task_execution_role_policy" {
  role       = aws_iam_role.ecs_task_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# CloudWatch Log Group for Django logs
resource "aws_cloudwatch_log_group" "django_logs" {
  name              = "/ecs/${var.service-name}-${var.deployment}"
  retention_in_days = 7
}
