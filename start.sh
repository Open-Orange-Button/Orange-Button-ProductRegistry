#!/bin/bash

# Enable bash debugging
set -x

# Ensure we're in the correct directory
cd /app || {
    echo "Failed to change to /app directory"
    exit 1
}

# Create required Nginx directories
mkdir -p /var/log/nginx
touch /var/log/nginx/access.log /var/log/nginx/error.log
chown -R www-data:www-data /var/log/nginx

# Create log directory if it doesn't exist
mkdir -p /app/logs
touch /app/logs/gunicorn-access.log /app/logs/gunicorn-error.log
chown -R www-data:www-data /app/logs
chmod 755 /app/logs

# Kill any existing Gunicorn processes
pkill gunicorn || true
sleep 2

# Apply database migrations with error handling
echo "Running database migrations..."
python3 manage.py migrate --noinput || {
    echo "Migration failed, checking if tables exist..."
    python3 manage.py migrate --fake-initial
}

# Collect static files
echo "Collecting static files..."
python3 manage.py collectstatic --noinput

# Set environment variables if not already set
# This allows override from container orchestration platforms
if [ -z "$ADDITIONAL_ALLOWED_HOSTS" ]; then
    # Get the container's IP address
    CONTAINER_IP=$(hostname -i || echo "")
    # Get the container's hostname
    CONTAINER_HOSTNAME=$(hostname -f || echo "")
    
    # Combine any additional hosts needed for this environment
    export ADDITIONAL_ALLOWED_HOSTS="${CONTAINER_IP},${CONTAINER_HOSTNAME}"
    echo "Setting additional allowed hosts: ${ADDITIONAL_ALLOWED_HOSTS}"
fi

# Start Gunicorn in the background with increased debugging
echo "Starting Gunicorn..."
gunicorn product_registry.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --timeout 120 \
    --access-logfile /app/logs/gunicorn-access.log \
    --error-logfile /app/logs/gunicorn-error.log \
    --capture-output \
    --log-level debug \
    --worker-class sync \
    --max-requests 1000 \
    --max-requests-jitter 50 \
    --backlog 2048 \
    --preload \
    --pid /app/logs/gunicorn.pid &

# Wait for Gunicorn to start and verify it's responding
echo "Waiting for Gunicorn to start..."
max_retries=30
counter=0

# Function to check Gunicorn status
check_gunicorn() {
    local response
    response=$(curl -s -o /dev/null -w "%{http_code}" http://0.0.0.0:8000/health/)
    if [ "$response" = "200" ]; then
        return 0
    fi
    return 1
}

# Wait for Gunicorn with better debugging
while ! check_gunicorn && [ $counter -lt $max_retries ]; do
    echo "Waiting for Gunicorn... Attempt $((counter+1))/$max_retries"
    echo "Current Gunicorn processes:"
    ps aux | grep gunicorn
    echo "Checking port 8000:"
    netstat -tlpn | grep 8000 || true
    echo "Gunicorn error log tail:"
    tail -n 5 /app/logs/gunicorn-error.log
    sleep 2
    counter=$((counter+1))
done

if [ $counter -eq $max_retries ]; then
    echo "Gunicorn failed to start properly"
    echo "Gunicorn error log:"
    cat /app/logs/gunicorn-error.log
    echo "Gunicorn access log:"
    cat /app/logs/gunicorn-access.log
    echo "Process list:"
    ps aux
    echo "Port status:"
    netstat -tlpn
    exit 1
fi

echo "Gunicorn is running and responding"

# Configure and start Nginx
echo "Configuring Nginx..."
nginx -t || {
    echo "Nginx configuration test failed"
    exit 1
}

echo "Starting Nginx..."
nginx -g 'daemon off;'