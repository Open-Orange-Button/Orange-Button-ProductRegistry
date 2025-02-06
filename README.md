# Orange Button Product Registry Documentation

## Table of Contents
1. [About Orange Button Product Registry](#about)
2. [Live Application Access](#live-access)
3. [Local Deployment](#local-deployment)
4. [Development Setup](#development-setup)
5. [Architecture Overview](#architecture)
6. [Configuration](#configuration)
7. [Dependencies](#dependencies)
8. [Troubleshooting](#troubleshooting)

<a name="about"></a>
## About Orange Button Product Registry
Orange Button Product Registry is a centralized platform for managing and registering Solar, Batteries and Inverters products. It enables users to:
- Register and manage solar industry products
- Upload and validate product data
- Access standardized product information
- Integrate with Orange Button data standards
- Synchorinzed datasets with CEC Database

<a name="live-access"></a>
## Live Application Access

### Main Application
1. Visit [https://productregistry.oballiance.org](https://productregistry.oballiance.org)
2. Navigate to the product listing at `/product/`

### Health Monitoring
- Health endpoint: [https://productregistry.oballiance.org/health](https://productregistry.oballiance.org/health)
- Returns "OK" if the service is healthy
- Used by load balancers for health checks

<a name="local-deployment"></a>
## Local Deployment on Docker for Development Setup

### Clone and Build Locally
1. Clone the repository:
   ```bash
   git clone https://github.com/Vishganti/Orange-Button-ProductRegistry.git
   cd Orange-Button-ProductRegistry
   ```

2. You can build and run the command using Docker Compose command
     ```bash
   docker-compose up --build -d
   ```
If you run into an error while running the docker container, thats mostly likely due to a db.conf file missing. Use the sample file provided and save it as db.cnf in the root directory and rebuild the container using the above commands

You can also build and run the container using the following commands 

1. Build the Docker image:
   ```bash
   docker build -t prodregapp-local .
   ```

2. Run locally:
   ```bash
   docker run -d \
     --name product-registry-dev \
     -p 80:80 \
     -p 8000:8000 \
     prodregapp-local
   ```


### Prerequisites to run deploy this in AWS Container Services
1. Install AWS CLI:
   ```bash
   # macOS (using Homebrew)
   brew install awscli

   # Windows
   # Download and run AWS CLI MSI installer from AWS website

   # Verify installation
   aws --version
   ```

2. Configure AWS CLI:
   ```bash
   aws configure
   # Enter your:
   # - AWS Access Key ID
   # - AWS Secret Access Key
   # - Default region (us-east-1)
   # - Output format (json)
   ```
   [AWS CLI Configuration Documentation](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-quickstart.html)

3. Install Docker:
   - [Docker Desktop for Mac](https://docs.docker.com/desktop/install/mac-install/)
   - [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/)

### Deploy from ECR
1. Authenticate with ECR:
   ```bash
   aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 545009828484.dkr.ecr.us-east-1.amazonaws.com
   ```

2. Pull the latest Docker image from Amazon Elastic Container Registry ECR:
   ```bash
   docker pull 545009828484.dkr.ecr.us-east-1.amazonaws.com/prodregapp:latest
   ```

3. Run the container:
   ```bash
   docker run -d \
     --name product-registry \
     -p 80:80 \
     -p 8000:8000 \
     545009828484.dkr.ecr.us-east-1.amazonaws.com/prodregapp:latest
   ```

4. Verify deployment:
   ```bash
   # Check container status
   docker ps

   # View logs
   docker logs -f product-registry

   # Test endpoints
   curl http://localhost/health/
   ```

<a name="architecture"></a>
## Architecture Overview

### Component Stack
1. **Nginx (Front Proxy)**
   - Serves on port 80
   - Handles static file serving
   - Proxies dynamic requests to Gunicorn
   - Manages SSL termination

2. **Gunicorn (WSGI Server)**
   - Runs on port 8000
   - 3 worker processes
   - 120-second timeout
   - Handles Django application serving

3. **Django (Application Server)**
   - Handles business logic
   - Manages database interactions
   - Processes API requests
   - Manages authentication

4. **MySQL (Database)**
   - Version 8.0.35 (required)
   - Case-sensitive collation
   - UTF8MB4 character set

### Request Flow
```
Client Request → Nginx → Gunicorn → Django → MySQL
                     ↳ Static Files
```

<a name="configuration"></a>
## Configuration

### Database Configuration
1. Create `db.cnf` file:
   ```cnf
   [client]
   database = your_database_name
   user = your_database_user
   password = your_database_password
   host = your_database_host
   port = 3306
   default-character-set = utf8mb4
   ```

2. Place in the db.cnf file in the root directory of the cloned repo `/Orange-Button-ProductRegistry/db.cnf`

### MySQL Requirements
```sql
-- Required MySQL version
MySQL 8.0.35

-- Collation settings
COLLATION = 'utf8mb4_0900_as_cs'
CHARACTER SET = utf8mb4

-- Example database creation
CREATE DATABASE product_registry_demo #change the databasename here 
  CHARACTER SET = 'utf8mb4'
  COLLATE = 'utf8mb4_0900_as_cs';
```

<a name="dependencies"></a>
## Dependencies
As of February 2025:

### Python Dependencies
```requirements.txt
Django==4.2.7
gunicorn==21.2.0
django-mysql==4.9.0
whitenoise==6.5.0
djangorestframework==3.14.0
```

### System Requirements
- Python 3.10+
- Nginx 1.18+
- MySQL 8.0.35
- Docker 24+

### Infrastructure
- AWS ECS (Fargate): The pre-built image uses ARM64/Linux Architecture 
- AWS ECR
- AWS ALB
- AWS RDS (MySQL 8.0.35)

<a name="troubleshooting"></a>
## Troubleshooting

### Common Issues
1. Database Connection:
   ```bash
   # Check MySQL connection
   docker exec product-registry mysql -h your_host -u your_user -p
   ```

2. Static Files:
   ```bash
   # Verify static files
   docker exec product-registry ls -la /root/Orange-Button-ProductRegistry/staticfiles/
   ```

3. Logs:
   ```bash
   # Application logs
   docker logs product-registry

   # Nginx access logs
   docker exec product-registry tail -f /var/log/nginx/access.log

   # Nginx error logs
   docker exec product-registry tail -f /var/log/nginx/error.log
   ```

### Health Checks
```bash
# Check Django health
curl http://localhost/health/

# Check Nginx status
docker exec product-registry nginx -t

# Check Gunicorn processes
docker exec product-registry ps aux | grep gunicorn
```

## Support and Resources
- [AWS Documentation](https://docs.aws.amazon.com/)
- [Django Documentation](https://docs.djangoproject.com/)
- [Nginx Documentation](https://nginx.org/en/docs/)
- [Docker Documentation](https://docs.docker.com/)

For issues or support:
1. Open a GitHub issue
2. Contact the maintainers
3. Check the project wiki

---

**Note**: Keep all dependencies updated and regularly check for security updates. Test thoroughly when upgrading any component, especially MySQL, as version compatibility is critical for proper operation.
