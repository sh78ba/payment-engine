#!/bin/sh

# Exit immediately if a command exits with a non-zero status
set -e

echo "Running migrations..."
python manage.py migrate

echo "Seeding merchants..."
python manage.py seed_merchants

echo "Starting Celery worker in background..."
celery -A config worker --loglevel=info --detach

echo "Starting Celery beat in background..."
celery -A config beat --loglevel=info --detach

echo "Starting Django server..."
# Render dynamically assigns a PORT environment variable.
# If it's not set, fallback to 8000.
PORT="${PORT:-8000}"
exec gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
