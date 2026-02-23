# 1. Load Balancer Security Group (Public)
resource "aws_security_group" "alb_sg" {
  name        = "${var.service-name}-alb-sg"
  vpc_id      = module.vpc.vpc_id
  description = "Allows public HTTP/HTTPS traffic"

  ingress {
    protocol    = "tcp"
    from_port   = 80
    to_port     = 80
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    protocol    = "tcp"
    from_port   = 443
    to_port     = 443
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# 2. ECS Task Security Group (Private)
resource "aws_security_group" "ecs_sg" {
  name        = "${var.service-name}-ecs-task-sg"
  vpc_id      = module.vpc.vpc_id
  description = "Allows traffic only from the Load Balancer"

  ingress {
    protocol        = "tcp"
    from_port       = 8000 # Standard Django port (change if using 80/443 in Docker)
    to_port         = 8000
    security_groups = [aws_security_group.alb_sg.id]
  }

  egress {
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["0.0.0.0/0"] # Needed to pull images and reach DB
  }
}

# 3. RDS MySQL Security Group (Private)
resource "aws_security_group" "rds_sg" {
  name        = "${var.service-name}-rds-sg"
  vpc_id      = module.vpc.vpc_id
  description = "Allows MySQL traffic only from ECS tasks"

  ingress {
    protocol        = "tcp"
    from_port       = 3306
    to_port         = 3306
    security_groups = [aws_security_group.ecs_sg.id, aws_security_group.bastion_sg.id]
  }

  egress {
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["0.0.0.0/0"]
  }
}
