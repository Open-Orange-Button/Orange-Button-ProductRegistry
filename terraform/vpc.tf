module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 6.6.0"

  name = "${var.service-name}-${var.deployment}-vpc"
  cidr = "10.0.0.0/16"

  # Use at least 2 Availability Zones for high availability
  azs             = var.availability-zones

  # Tier 1: Load Balancer (Public)
  public_subnets  = ["10.0.1.0/24", "10.0.2.0/24"]

  # Tier 2: ECS App Tasks (Private)
  private_subnets = ["10.0.10.0/24", "10.0.11.0/24"]

  # Tier 3: MySQL Database (Private)
  database_subnets = ["10.0.20.0/24", "10.0.21.0/24"]

  # Enable NAT Gateway so private ECS tasks can pull Docker images from ECR
  # and talk to external APIs
  enable_nat_gateway = true
  single_nat_gateway = true # Set to false in production for better HA

  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Environment = var.deployment
    Project     = var.service-name
  }
}
