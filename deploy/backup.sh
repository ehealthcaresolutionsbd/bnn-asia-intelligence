#!/bin/sh
# Nightly: crontab -e →  15 2 * * * /opt/bnn-intel/deploy/backup.sh
set -e
cd "$(dirname "$0")"
TS=$(date +%Y%m%d-%H%M)
mkdir -p backups
docker compose exec -T db pg_dump -U bnn -Fc bnn_intel > "backups/bnn_intel-$TS.dump"
docker compose run --rm -v "$PWD/backups:/b" web sh -c "tar czf /b/media-$TS.tgz -C /app media"
find backups -type f -mtime +30 -delete
# Restore: docker compose exec -T db pg_restore -U bnn -d bnn_intel --clean < backups/bnn_intel-YYYYMMDD-HHMM.dump
