# Use Ubuntu 22.04 as the base image
FROM ubuntu:22.04

# Prevent apt from asking for user input
ENV DEBIAN_FRONTEND=noninteractive

# Set the working directory
WORKDIR /app

# Install system dependencies and Nginx
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    python3 \
    python3-pip \
    python3-mysqldb \
    libmysqlclient-dev \
    mysql-client \
    vim \
    pkg-config \
    libssl-dev \
    curl \
    nginx \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip3 install --no-cache-dir -r requirements.txt

# Create necessary directories and set permissions
RUN mkdir -p /app/logs \
    && mkdir -p /app/staticfiles/server \
    && mkdir -p /app/static \
    && touch /app/logs/django.log \
    && chmod -R 755 /app/logs \
    && chmod -R 755 /app/staticfiles \
    && chmod -R 755 /app/static

# Copy the application files
COPY . .

# Copy database configuration
COPY db.cnf /etc/Orange-Button-ProductRegistry/db.cnf

# Remove all default Nginx configurations and set up our own
RUN rm -f /etc/nginx/sites-enabled/default \
    && rm -f /etc/nginx/sites-available/default \
    && rm -f /etc/nginx/conf.d/default.conf \
    && rm -rf /etc/nginx/conf.d/*.conf
COPY nginx.conf /etc/nginx/nginx.conf

# Copy startup script
COPY start.sh /start.sh
RUN chmod +x /start.sh

# Create static files directory and set permissions
RUN mkdir -p /app/staticfiles/server \
    && mkdir -p /app/server/static/server \
    && chown -R www-data:www-data /app \
    && chmod -R 755 /app/staticfiles/ \
    && chmod -R 755 /app/server/static/

# Create required Nginx directories and set permissions
RUN mkdir -p /var/log/nginx \
    && touch /var/log/nginx/access.log /var/log/nginx/error.log \
    && chown -R www-data:www-data /var/log/nginx \
    && chmod -R 755 /var/log/nginx

# Expose both Nginx and Gunicorn ports
EXPOSE 80 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost/health/ || exit 1

# Start Nginx and Gunicorn
CMD ["/start.sh"]