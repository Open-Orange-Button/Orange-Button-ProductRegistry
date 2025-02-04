# Use Ubuntu 22.04 as the base image
FROM ubuntu:22.04

# Prevent apt from asking for user input
ENV DEBIAN_FRONTEND=noninteractive

# Set the working directory
WORKDIR /root/Orange-Button-ProductRegistry

# Install system dependencies and Nginx
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    python3 \
    python3-pip \
    python3-venv \
    libmysqlclient-dev \
    mysql-client \
    vim \
    pkg-config \
    libssl-dev \
    curl \
    nginx \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /root/Orange-Button-ProductRegistry/.venv

# Set environment variables
ENV PATH="/root/Orange-Button-ProductRegistry/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy database configuration
COPY db.cnf /etc/Orange-Button-ProductRegistry/db.cnf

# Copy Nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy the application files
COPY . .

# Copy startup script
COPY start.sh /start.sh
RUN chmod +x /start.sh

# Create necessary directories and set permissions
RUN mkdir -p /root/Orange-Button-ProductRegistry/logs \
    && mkdir -p /root/Orange-Button-ProductRegistry/staticfiles \
    && touch /root/Orange-Button-ProductRegistry/logs/django.log \
    && chmod -R 755 /root/Orange-Button-ProductRegistry/logs

# Run collectstatic and set permissions
RUN python manage.py collectstatic --noinput \
    && chmod -R 755 /root/Orange-Button-ProductRegistry/staticfiles/ \
    && chmod -R 755 /root/Orange-Button-ProductRegistry/

# Remove default nginx site config
RUN rm -f /etc/nginx/sites-enabled/default

# Expose both Nginx and Gunicorn ports
EXPOSE 80 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost/health/ || exit 1

# Start Nginx and Gunicorn
CMD ["/start.sh"]