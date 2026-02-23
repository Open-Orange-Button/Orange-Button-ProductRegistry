# 1. Task Definition: The "Blueprint"
resource "aws_ecs_task_definition" "app" {
  family                   = "${var.service-name}-app"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  # https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html
  cpu                      = "1024"
  memory                   = "4096"
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn

  container_definitions = jsonencode([{
    name      = "${var.service-name}-app"
    image     = "${aws_ecr_repository.app.repository_url}:latest"
    essential = true

    portMappings = [{
      containerPort = 8000
      hostPort      = 8000
      protocol = "tcp"
    }]

    # Environment variables for Django settings
    environment = [
      { name = "DB_HOST", value = aws_db_instance.mysql.address },
      { name = "DB_NAME", value = aws_db_instance.mysql.db_name },
      { name = "DB_USER", value = aws_db_instance.mysql.username },
      { name = "DB_PASS", value = aws_db_instance.mysql.password }, # Use Secrets Manager in prod!
      { name = "ALLOWED_HOSTS", value = "*" } # Narrow this down to your domain later
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.django_logs.name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "django"
      }
    }
  }])
}

# 2. ECS Service: The "Process Manager"
resource "aws_ecs_service" "main" {
  name            = "${var.service-name}-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = 2 # High Availability (runs 2 copies of your app)
  launch_type     = "FARGATE"

  network_configuration {
    security_groups  = [aws_security_group.ecs_sg.id]
    subnets          = module.vpc.private_subnets
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = "${var.service-name}-app"
    container_port   = 8000
  }

  # Ensure the DB is ready before the service starts
  depends_on = [aws_db_instance.mysql, aws_lb_listener.http]

  health_check_grace_period_seconds = 30
}
