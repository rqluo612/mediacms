#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/mediacms}"
BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/mediacms}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
ENV_FILE="${ENV_FILE:-${PROJECT_DIR}/.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-${PROJECT_DIR}/docker-compose-prod.yaml}"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Missing environment file: ${ENV_FILE}" >&2
    exit 1
fi

if [[ "${BACKUP_ROOT}" != /* || "${BACKUP_ROOT}" == "/" ]]; then
    echo "BACKUP_ROOT must be a non-root absolute path." >&2
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
destination="${BACKUP_ROOT}/${timestamp}"
mkdir -p "${destination}"
chmod 700 "${BACKUP_ROOT}" "${destination}"

docker compose \
    --env-file "${ENV_FILE}" \
    -f "${COMPOSE_FILE}" \
    exec -T db \
    pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -Fc \
    > "${destination}/database.dump"

tar -C "${PROJECT_DIR}" -czf "${destination}/media_files.tar.gz" media_files
chmod 600 "${destination}/database.dump" "${destination}/media_files.tar.gz"

sha256sum \
    "${destination}/database.dump" \
    "${destination}/media_files.tar.gz" \
    > "${destination}/SHA256SUMS"

find "${BACKUP_ROOT}" -mindepth 1 -maxdepth 1 -type d -mtime "+${RETENTION_DAYS}" -exec rm -rf -- {} +
echo "Backup completed: ${destination}"
