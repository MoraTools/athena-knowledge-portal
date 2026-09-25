#!/bin/sh
set -eu
cd /opt/athena
id athena >/dev/null 2>&1 || useradd --system --home /var/lib/athena --shell /usr/sbin/nologin athena
install -d -m 700 -o athena -g athena /var/lib/athena
install -d -m 700 /etc/athena
if [ ! -f /etc/athena/athena.env ]; then
    python3 - <<'PY'
import os, secrets
fd = os.open('/etc/athena/athena.env', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as file:
    file.write('ATHENA_SECRET_KEY=' + secrets.token_urlsafe(64) + '\n')
    file.write('ATHENA_HOSTS=athena.moratechnology.com\nATHENA_DATA_DIR=/var/lib/athena\n')
PY
fi
# WeasyPrint (article PDF export) needs Pango, HarfBuzz subsetting, and the DejaVu fonts.
apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core
python3 -m venv .venv
.venv/bin/pip install --disable-pip-version-check -r requirements.txt
set -a
. /etc/athena/athena.env
set +a
.venv/bin/python server/manage.py migrate --noinput
if [ ! -f /var/lib/athena/.import-complete ]; then
    .venv/bin/python server/manage.py import_portal
    touch /var/lib/athena/.import-complete
fi
.venv/bin/python server/manage.py bootstrap_admin --output /etc/athena/initial-admin.txt
.venv/bin/python server/manage.py collectstatic --noinput
.venv/bin/python server/manage.py check --deploy --fail-level WARNING
chown -R athena:athena /var/lib/athena
chmod -R go-rwx /var/lib/athena
# Code is readable but not writable by the web process.
chmod -R a+rX /opt/athena/src /opt/athena/dist /opt/athena/server /opt/athena/staticfiles
install -m 644 deploy/athena.service deploy/athena-backup.service deploy/athena-backup.timer /etc/systemd/system/
install -m 644 deploy/Caddyfile /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile
systemctl daemon-reload
systemctl enable --now athena athena-backup.timer
systemctl restart athena
systemctl reload caddy
systemctl start athena-backup
systemctl is-active athena caddy
