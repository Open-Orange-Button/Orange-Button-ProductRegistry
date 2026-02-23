# 1. Security Group for Bastion Host
resource "aws_security_group" "bastion_sg" {
  name        = "${var.service-name}-bastion-sg"
  vpc_id      = module.vpc.vpc_id
  description = "Allow SSH access from my local IP"

  ingress {
    protocol    = "tcp"
    from_port   = 22
    to_port     = 22
    cidr_blocks = ["<your_IP>/32"] # Replace with your actual public IP
  }

  egress {
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# 2. Key Pair for SSH Access
# You must create this key locally first: ssh-keygen -f bastion_key
resource "aws_key_pair" "bastion_key" {
  key_name   = "bastion-key"
  public_key = file("bastion_key.pub")
}

# 3. Bastion EC2 Instance (Amazon Linux 2023)
resource "aws_instance" "bastion" {
  ami                         = "ami-02777684819ca2214"
  instance_type               = "t3.micro"
  subnet_id                   = module.vpc.public_subnets[0]
  vpc_security_group_ids      = [aws_security_group.bastion_sg.id]
  key_name                    = aws_key_pair.bastion_key.key_name
  associate_public_ip_address = true

  tags = { Name = "${var.service-name}-Bastion" }
}

# Output the Public IP for connection
output "bastion_public_ip" {
  value = aws_instance.bastion.public_ip
}

# resource "aws_security_group_rule" "allow_bastion_to_rds" {
#   type                     = "ingress"
#   from_port                = 3306
#   to_port                  = 3306
#   protocol                 = "tcp"
#   security_group_id        = aws_security_group.rds_sg.id
#   source_security_group_id = aws_security_group.bastion_sg.id
# }
