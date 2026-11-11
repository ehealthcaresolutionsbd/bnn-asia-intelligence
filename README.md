# BNN Asia – Country Intelligence & Asia Ranking Platform (2026 Edition)

```
backend/     Django 5.2 + DRF + PostgreSQL + Celery/Redis  → api.bnnasia.org / research.bnnasia.org
wordpress/   "BNN Asia Intelligence Connector" plugin (zip ready to upload)
deploy/      docker-compose stack, nginx, .env.example, backup.sh
docs/        methodology, sample (DRAFT) PDF report
elementor/   the converter used to rebuild bnnasia.org pages as native Elementor
```

## Local development
```bash
cd backend
pip install -r requirements.txt
createdb bnn_intel            # or set DATABASE_URL
python manage.py migrate
python manage.py seed_platform          # countries, 2026 period, categories, indicators, sources, draft methodology
python manage.py test_integrations      # tests every data source, updates the integration registry
python manage.py sync_sources           # pulls live data from working sources
python manage.py aggregate_incidents    # verified incidents → indicators
python manage.py calculate_ranking      # DRAFT snapshot (add --publish only after editorial sign-off)
python manage.py test apps.api          # 22 tests
python manage.py createsuperuser && python manage.py runserver
```

## Production (api.bnnasia.org, research.bnnasia.org)
1. DNS: A records for `api` and `research` → server IP.
2. `cp deploy/.env.example deploy/.env` and fill secrets.
3. `certbot certonly --standalone -d api.bnnasia.org -d research.bnnasia.org`
4. `cd deploy && docker compose up -d --build`
5. `docker compose exec web python manage.py seed_platform && docker compose exec web python manage.py createsuperuser`
6. research.bnnasia.org/admin → API clients → add "bnnasia.org" → copy key once.
7. WordPress → Plugins → upload `wordpress/bnn-asia-intelligence-connector.zip` → Settings → BNN Intelligence → paste API URL + key.
8. Backups: `crontab: 15 2 * * * /opt/bnn-intel/deploy/backup.sh` (30-day retention; restore command inside the script).

## New edition (2027)
Admin → Reporting periods → add 2027 (start/end, mark current) → Ranking methodologies → new version for 2027.
No code changes needed.
