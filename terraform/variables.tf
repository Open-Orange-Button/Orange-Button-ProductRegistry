variable "service-name" {
    description = "The name of the web service to be launched."
    default = "ob-product-registry-2026-02"
}

variable "service-name-alphanumeric" {
    description = "The name of the web service only containing alphanumeric characters. Needed for RDS names."
    default = "OBProductRegistry"
}

variable "service-domain-name" {
    description = "The domain name of the web service."
    default = "productregistry.oballiance.org"
}

variable "deployment" {
    description = "The deployment is for production or development."
    default = "production"
}

variable "region" {
    description = "The AWS region to create resources in."
    default = "us-east-1"
}

variable "availability-zones" {
    description = "The AWS availability zones in the region."
    type = list(string)
    default = ["us-east-1a", "us-east-1b"]
}

# load balancer

variable "health-check-path" {
  description = "Health check path for the default target group."
  default     = "/health/"
}

# ecs

variable "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  default     = "production"
}

variable "docker_image_url_django" {
  description = "Docker image to run in the ECS cluster"
  default     = "<AWS_ACCOUNT_ID>.dkr.ecr.us-west-1.amazonaws.com/django-app:latest"
}

variable "app_count" {
  description = "Number of Docker containers to run"
  default     = 2
}

variable "fargate_cpu" {
  description = "Amount of CPU for Fargate task. E.g., '256' (.25 vCPU)"
  default     = "256"
}

variable "fargate_memory" {
  description = "Amount of memory for Fargate task. E.g., '512' (0.5GB)"
  default     = "512"
}
