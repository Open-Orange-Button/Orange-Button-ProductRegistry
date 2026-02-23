# 1. Create the ECR Repository
resource "aws_ecr_repository" "app" {
  name                 = "${var.service-name}-repo"
  image_tag_mutability = "MUTABLE"

  # Scans your images for software vulnerabilities on push
  # image_scanning_configuration {
    # scan_on_push = true
  # }
}

# 2. Lifecycle Policy (Keep only the last 2 images)
resource "aws_ecr_lifecycle_policy" "cleanup" {
  repository = aws_ecr_repository.app.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 2 images"
      selection = {
        tagStatus     = "any"
        countType     = "imageCountMoreThan"
        countNumber   = 1
      }
      action = {
        type = "expire"
      }
    }]
  })
}

# Output the Repository URL for your CI/CD or CLI login
output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}
