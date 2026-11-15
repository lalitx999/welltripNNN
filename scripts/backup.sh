#!/bin/sh
# Daily backup of the WellTrip database and uploaded media (run on the VPS from the project folder).
#   ./scripts/backup.sh            -> writes to ./backups, keeps the last 14 days
#   KEEP_DAYS=30 ./scripts/backup.sh
# Cron (03:15 every day):
#   15 3 * * * cd /path/to/welltrip && ./scripts/backup.sh >> backups/backup.log 2>&1
set -eu

cd "$(dirname "$0")/.."
BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Database: custom format, restore with pg_restore (see DEPLOY.md)
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' > "$BACKUP_DIR/db-$STAMP.dump.tmp"
mv "$BACKUP_DIR/db-$STAMP.dump.tmp" "$BACKUP_DIR/db-$STAMP.dump"

# Media: room photos, products, payment slips
docker compose exec -T backend tar czf - -C /app/media . > "$BACKUP_DIR/media-$STAMP.tgz.tmp"
mv "$BACKUP_DIR/media-$STAMP.tgz.tmp" "$BACKUP_DIR/media-$STAMP.tgz"

chmod 600 "$BACKUP_DIR"/db-"$STAMP".dump "$BACKUP_DIR"/media-"$STAMP".tgz
find "$BACKUP_DIR" -maxdepth 1 \( -name 'db-*.dump' -o -name 'media-*.tgz' \) -mtime +"$KEEP_DAYS" -delete

echo "$(date '+%F %T') backup ok: db-$STAMP.dump media-$STAMP.tgz"
