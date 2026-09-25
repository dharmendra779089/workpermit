#!/usr/bin/env bash
set -e

echo "==> Running database migrations..."
python manage.py migrate --noinput

echo "==> Seeding initial CMMS data..."
python manage.py seed_data

echo "==> Starting Gunicorn server on port ${PORT:-8080}..."
exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8080} --log-file -
