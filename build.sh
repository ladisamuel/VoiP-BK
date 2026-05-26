#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt


# Auto-generate migrations if the migration file is missing
if [ ! -f "calls/migrations/0001_initial.py" ]; then
    echo "Migration files not found. Generating..."
    python manage.py makemigrations calls
fi

python manage.py makemigrations
python manage.py migrate --run-syncdb

python manage.py migrate
python manage.py collectstatic --noinput
