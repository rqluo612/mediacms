# MediaCMS production deployment

This deployment keeps the MediaCMS application bound to `127.0.0.1:8080`.
Only the host Nginx reverse proxy exposes ports 80 and 443.

## Server baseline

- Ubuntu 24.04 LTS
- At least 4 vCPU, 8 GB RAM and sufficient SSD storage for source videos,
  encoded renditions and backups
- Docker Engine with the Compose plugin
- Nginx and Certbot installed on the host
- DNS A/AAAA records pointing the media domain to the server

## Prepare the application

Clone this repository to `/opt/mediacms`, then:

```bash
cd /opt/mediacms
cp .env.production.example .env.production
chmod 600 .env.production
mkdir -p data/postgres data/redis media_files /var/backups/mediacms
```

Generate secrets and place the results in `.env.production`:

```bash
openssl rand -base64 48
openssl rand -base64 36
openssl rand -base64 36
```

Use the values for `SECRET_KEY`, `POSTGRES_PASSWORD`, and `ADMIN_PASSWORD`.
Replace every `example.com` value and do not use `admin` as the administrator
username.

Validate and start:

```bash
docker compose --env-file .env.production -f docker-compose-prod.yaml config
docker compose --env-file .env.production -f docker-compose-prod.yaml pull
docker compose --env-file .env.production -f docker-compose-prod.yaml up -d
docker compose --env-file .env.production -f docker-compose-prod.yaml ps
```

When restoring an existing MediaCMS database, `ADMIN_PASSWORD` does not update
an existing user. Change the password explicitly and disable the old default
administrator account:

```bash
docker compose --env-file .env.production -f docker-compose-prod.yaml \
  exec web python manage.py changepassword YOUR_ADMIN_USERNAME
```

## HTTPS reverse proxy

Copy `deploy/production/nginx-mediacms.conf` to
`/etc/nginx/sites-available/mediacms`, replace `video.example.com`, and enable
the site. Also replace `203.0.113.10` with the administrator's fixed public IP
or restrict `/admin/` to a VPN. Obtain the first certificate before enabling
the TLS server block:

```bash
sudo certbot certonly --nginx -d video.example.com
sudo nginx -t
sudo systemctl reload nginx
sudo certbot renew --dry-run
```

Open only TCP 22, 80 and 443 in the cloud firewall. Port 8080 must remain bound
to localhost and PostgreSQL/Redis must never be exposed publicly.

## Backup

Install the backup script and test it:

```bash
sudo install -m 750 deploy/production/backup.sh /usr/local/sbin/mediacms-backup
sudo PROJECT_DIR=/opt/mediacms /usr/local/sbin/mediacms-backup
```

Example daily cron entry:

```cron
20 3 * * * root PROJECT_DIR=/opt/mediacms /usr/local/sbin/mediacms-backup >> /var/log/mediacms-backup.log 2>&1
```

Copy backups to a second machine or object-storage bucket. A backup stored only
on the MediaCMS server is not sufficient.

## Migrate existing data

Create a PostgreSQL custom-format dump and a media archive on the old machine.
Transfer them over SSH or an encrypted object-storage channel:

```bash
scp database.dump media_files.tar.gz deploy-user@SERVER_IP:/opt/mediacms/import/
```

On the new server, stop workers while restoring:

```bash
cd /opt/mediacms
docker compose --env-file .env.production -f docker-compose-prod.yaml stop web celery_worker celery_beat
docker compose --env-file .env.production -f docker-compose-prod.yaml \
  exec -T db pg_restore --clean --if-exists --no-owner \
  -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" < import/database.dump
tar -xzf import/media_files.tar.gz -C /opt/mediacms
docker compose --env-file .env.production -f docker-compose-prod.yaml up -d
```

Run the password-change command after the restore. Keep the old server private
but intact until the HTTPS acceptance tests and a restore test have passed.

## Release checks

- `DEBUG=False`
- Default `admin/admin` credentials no longer work
- `/admin/` is restricted by IP or VPN at the host Nginx/firewall layer
- Anonymous users can access only public media
- Private media and original files cannot be fetched without authorization
- Upload, encoding, playback, comments and playlists work through HTTPS
- Cookies carry the `Secure` flag and POST requests pass CSRF validation
- Database and media backups can both be restored in a staging environment

`manage.py check --deploy` may intentionally retain warnings for HSTS preload,
HSTS subdomains and `X_FRAME_OPTIONS=DENY`. Do not enable HSTS preload or
subdomain coverage until every subdomain is permanently HTTPS-only. MediaCMS
keeps same-origin framing support for its embed/LMS features.
