#!/bin/bash
# Sauvegarde quotidienne : base PostgreSQL + images téléversées. Garde 14 jours.
# Installé par cron (voir le guide) : /usr/local/bin/backup-livres.sh
set -euo pipefail
DEST=/var/backups/livres
DATE=$(date +%F)
mkdir -p "$DEST"
sudo -u postgres pg_dump livres | gzip > "$DEST/db-$DATE.sql.gz"
tar -czf "$DEST/uploads-$DATE.tar.gz" -C /srv/livres/static uploads
find "$DEST" -type f -mtime +14 -delete
echo "Sauvegarde OK : $DEST ($DATE)"
