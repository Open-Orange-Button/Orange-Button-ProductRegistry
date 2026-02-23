#!/bin/sh

uv run python manage.py migrate --noinput
uv run python manage.py collectstatic --noinput

if [ -z "$ADDITIONAL_ALLOWED_HOSTS" ]; then
    # Get the container's IP address
    CONTAINER_IP=$(hostname -i || echo "")
    # Get the container's hostname
    CONTAINER_HOSTNAME=$(hostname -f || echo "")

    # Combine any additional hosts needed for this environment
    export ADDITIONAL_ALLOWED_HOSTS="${CONTAINER_IP},${CONTAINER_HOSTNAME}"
    echo "Setting additional allowed hosts: ${ADDITIONAL_ALLOWED_HOSTS}"
fi

uv run gunicorn product_registry.wsgi:application --bind 0.0.0.0:8000 --log-level info
