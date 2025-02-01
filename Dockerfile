# Use Ubuntu 22.04 as the base image
FROM ubuntu:22.04

SHELL ["/bin/bash", "-c"]

# Install system dependencies
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt install -y \
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
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /root/Orange-Button-ProductRegistry

# Copy the application files to the container
COPY . /root/Orange-Button-ProductRegistry

# Create and activate a virtual environment
RUN python3 -m venv /root/Orange-Button-ProductRegistry/.venv

# ✅ Ensure virtual environment is used by default
ENV PATH="/root/Orange-Button-ProductRegistry/.venv/bin:$PATH"

# Install Python dependencies inside the virtual environment
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy database configuration
COPY db.cnf /etc/Orange-Button-ProductRegistry/db.cnf

# Expose the Django development server port
EXPOSE 8000

# Run migrations and start Django automatically and keep the container running
CMD ["bash", "-c", "python manage.py makemigrations && python manage.py migrate && /root/Orange-Button-ProductRegistry/.venv/bin/gunicorn --bind 0.0.0.0:8000 --workers 3 --timeout 120 --access-logfile - --error-logfile - product_registry.wsgi:application"]