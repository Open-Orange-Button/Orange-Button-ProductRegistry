# Create the DB Subnet Group (assigns RDS to our private database subnets)
resource "aws_db_subnet_group" "mysql" {
  name       = "${var.service-name}-db-subnet-group"
  subnet_ids = module.vpc.database_subnets

  tags = { Name = "${var.service-name} DB Subnet Group" }
}

resource "aws_db_parameter_group" "mysql_collation_pg" {
  name   = "mysql-collation-parameter-group"
  family = "mysql8.4" # Use the appropriate family for your engine version

  # Set the server character set
  parameter {
    name  = "character_set_server"
    value = "utf8mb4"
  }

  # Set the server collation
  parameter {
    name  = "collation_server"
    value = "utf8mb4_0900_as_cs" # Example: a different collation
  }
}

# The MySQL RDS Instance
resource "aws_db_instance" "mysql" {
  identifier            = "${var.service-name}-db-instance"
  engine                = "mysql"
  engine_version        = "8.4.8"
  instance_class        = "db.t4g.micro" # Free-tier eligible / Small dev size
  allocated_storage     = 20
  max_allocated_storage = 20 # Allows auto-scaling storage

  db_name  = var.service-name-alphanumeric
  username = "admin"
  password = "your_secure_password" # In production, use a Secret Manager variable

  parameter_group_name = aws_db_parameter_group.mysql_collation_pg.name

  db_subnet_group_name   = aws_db_subnet_group.mysql.name
  vpc_security_group_ids = [aws_security_group.rds_sg.id]

  # Ensure the DB is not accessible from the public internet
  publicly_accessible = false
  skip_final_snapshot = true # Set to false for production to prevent data loss
  multi_az            = false # Set to true for production high availability
}
