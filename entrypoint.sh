#!/bin/sh
set -eu
python manage.py migrate --noinput
python manage.py bootstrap_demo
exec gunicorn tplab2.wsgi:application --bind 0.0.0.0:8000 --workers 2 --access-logfile -
