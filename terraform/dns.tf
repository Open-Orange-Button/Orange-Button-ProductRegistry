# 1. Create the Hosted Zone in Route 53
resource "aws_route53_zone" "main" {
  name = var.service-domain-name # Replace with your GoDaddy domain
}

# 2. Point the domain to the ALB (Alias Record)
resource "aws_route53_record" "app" {
  zone_id = aws_route53_zone.main.zone_id
  name    = var.service-domain-name # Root domain
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}

# Output the Nameservers (You will copy these into GoDaddy)
output "route53_nameservers" {
  value       = aws_route53_zone.main.name_servers
  description = "Copy these 4 nameservers into your GoDaddy DNS settings."
}
