#!/bin/bash
set -e

echo "Creating logs directory if it doesn't exist..."
mkdir -p /root/Orange-Button-ProductRegistry/logs

echo "Setting correct permissions..."
chmod -R 755 /root/Orange-Button-ProductRegistry/staticfiles/
chmod -R 755 /root/Orange-Button-ProductRegistry/logs/

echo "Checking Django configuration..."
python << END
from django.conf import settings
try:
    settings.configure()
    print("Django settings configured successfully")
except Exception as e:
    print(f"Error configuring Django settings: {e}")
    exit(1)
END

echo "Ensuring Nginx is stopped..."
service nginx stop || true

echo "Running database migrations..."
python manage.py migrate --noinput

echo "Starting Nginx..."
service nginx start

echo "Checking Nginx configuration..."
nginx -t

echo "Starting Gunicorn..."
exec gunicorn --bind 0.0.0.0:8000 \
    --workers 3 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    --log-level debug \
    --capture-output \
    product_registry.wsgi:application