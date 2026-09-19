# Deploying the Randomizer Site

> **Note**: This document was written by Claude and edited by jdharms.

The site runs on one Ubuntu VPS at `https://nesopengolf.com`. The files it is deployed
with are in `deploy/`; this is how they fit together, how a fresh server is set up, and how
a release is deployed, rolled back and restored.

## Shape

| Piece | What it is | Configured by |
|---|---|---|
| Caddy | Reverse proxy on ports 80 and 443; obtains and renews certificates, redirects `www` and HTTP to `https://nesopengolf.com` | `deploy/Caddyfile` at `/etc/caddy/Caddyfile` |
| `golf-site` | The site under uvicorn, one worker, on `127.0.0.1:8000`, as the system user `golf` | `deploy/golf-site.service` at `/etc/systemd/system/golf-site.service` |
| Site configuration | The `GOLF_` variables, root-owned mode 0600, read by systemd | `deploy/golf-site.env.example` filled in at `/etc/golf-site/env` |
| Litestream | Replicates the database to S3-compatible object storage | `deploy/litestream.yml` at `/etc/litestream.yml`, with its keys in `/etc/litestream.env` through `deploy/litestream-credentials.conf` |
| Releases | A git checkout of a tag, with its locked dependencies | `deploy/deploy.sh` |

The QR codes built into every ROM point at `https://nesopengolf.com/s/` (`URL_PREFIX` in
`golf/qr/payload.py`), so the bare domain is the site, and `www` only redirects.

On the server:

| Path | Holds | Owner |
|---|---|---|
| `/opt/golf-site` | The checkout and its `.venv` | the admin user |
| `/opt/uv/python` | The Python uv installs for the `.venv` (`.python-version`) | the admin user |
| `/var/lib/golf-site/golf_site.db` | The database (`GOLF_DATABASE`) | `golf` |
| `/var/lib/golf-site/roms` | The vanilla ROMs (`GOLF_ROM_DIR`), mode 0700 | `golf` |
| `/var/lib/golf-site/courses` | The hole store (`GOLF_HOLES_DIR`) | `golf` |
| `/var/lib/golf-site/rangefinder` | The rangefinder's renders (`GOLF_RANGEFINDER_DIR`) | `golf` |

The service can write only `/var/lib/golf-site`; the checkout and the rest of the system
are read-only to it. Before each start it runs `golf-rehydrate --check`, and a full
`golf-rehydrate` only when that fails, so it always serves holes and renders verified
against the catalog.

Run exactly one uvicorn worker. The rate limiter and the database lock live in the
process, and a second worker would split both.

## Setting up a server

Once, on a fresh Ubuntu server. Commands run as an admin user with sudo.

### Base system

1. Create the admin user with an SSH key, then set `PasswordAuthentication no` and
   `PermitRootLogin no` in `/etc/ssh/sshd_config` and restart `ssh`.
2. Firewall: `sudo ufw allow OpenSSH`, `sudo ufw allow 80,443/tcp`, `sudo ufw enable`.
3. Security updates: `sudo apt install unattended-upgrades` and
   `sudo dpkg-reconfigure unattended-upgrades`.
4. On a server with 1 GB of memory, add a swap file.
5. `sudo apt install git curl sqlite3`.

### DNS

`A` and `AAAA` records for `nesopengolf.com` pointing at the server, and
`www.nesopengolf.com` a `CNAME` to `nesopengolf.com`. No wildcard record.

### Software

- **uv**: `curl -LsSf https://astral.sh/uv/install.sh | sudo env UV_INSTALL_DIR=/usr/local/bin sh`
- **Caddy**: from Caddy's own apt repository, following
  <https://caddyserver.com/docs/install#debian-ubuntu-raspbian>.
- **Litestream**: the `.deb` for the server's architecture from
  <https://github.com/benbjohnson/litestream/releases>, installed with `sudo apt install ./litestream-*.deb`.

### The site

```bash
sudo useradd --system --home-dir /var/lib/golf-site --shell /usr/sbin/nologin golf
sudo install -d -o golf -g golf -m 0750 /var/lib/golf-site
sudo install -d -o golf -g golf -m 0700 /var/lib/golf-site/roms
sudo install -d -o "$USER" -g "$USER" /opt/golf-site /opt/uv

git clone https://github.com/jdharms/nes-open-tools.git /opt/golf-site
```

Copy the ROMs up (`scp nes_open_us.nes mario_open_jp.nes server:`), then install them
where only `golf` can read them:

```bash
sudo install -o golf -g golf -m 0400 nes_open_us.nes mario_open_jp.nes /var/lib/golf-site/roms/
rm nes_open_us.nes mario_open_jp.nes
```

Configuration: start from the example, keep its paths and base URL as they are, and
replace each `replace-me` with the Discord client id and secret, a new session secret and
the admins' Discord ids. Every line is needed.

```bash
sudo install -d -m 0755 /etc/golf-site
sudo install -m 0600 /opt/golf-site/deploy/golf-site.env.example /etc/golf-site/env
sudoedit /etc/golf-site/env
```

A session secret for `GOLF_SESSION_SECRET`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

The Discord application's redirect URI is `https://nesopengolf.com/auth/callback`.

The service, and the first deploy, which installs the dependencies and starts it:

```bash
sudo cp /opt/golf-site/deploy/golf-site.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable golf-site
/opt/golf-site/deploy/deploy.sh <tag>
```

### Caddy

With DNS pointing at the server:

```bash
sudo cp /opt/golf-site/deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
curl -fsS https://nesopengolf.com/healthz
```

### Litestream

Create a bucket and an access key limited to it. On Backblaze B2, set the bucket's
lifecycle rule to "Keep only the last version of the file": B2 keeps every version by
default, so the snapshots Litestream deletes past its retention would only be hidden and
would go on taking space. The bucket's details page shows its S3 endpoint, whose second
part is the region (`s3.us-west-004.backblazeb2.com` is in `us-west-004`).

Fill in the bucket, endpoint and region:

```bash
sudo cp /opt/golf-site/deploy/litestream.yml /etc/litestream.yml
sudoedit /etc/litestream.yml
sudo install -m 0600 /dev/null /etc/litestream.env
sudoedit /etc/litestream.env      # LITESTREAM_ACCESS_KEY_ID=... and LITESTREAM_SECRET_ACCESS_KEY=...
sudo install -D -m 0644 /opt/golf-site/deploy/litestream-credentials.conf \
    /etc/systemd/system/litestream.service.d/credentials.conf
sudo systemctl daemon-reload
sudo systemctl enable --now litestream
journalctl -u litestream -n 20
```

Then restore a copy (see "Restoring the database" below) to check the backups work.

### Kept elsewhere

Litestream holds only the database. `/etc/golf-site/env`, `/etc/litestream.env` and the
ROMs are not backed up by anything on the server; keep the secrets in a password manager
and the ROMs with your own copies.

### Checking it

- `https://nesopengolf.com/healthz` answers, and `http://` and `www.` redirect to it.
- Discord sign-in works and the header shows the signed-in name.
- Generate a seed, download a signed-in ROM, play a round and scan its QR code; the phone
  lands on the round's `/r/<id>` page.

## Deploying a release

Tag the commit and push the tag, from a development checkout:

```bash
git tag v1.0.0
git push origin v1.0.0
```

On the server:

```bash
/opt/golf-site/deploy/deploy.sh v1.0.0
```

It refuses a checkout with local changes or a tag that does not exist, prints the release
it replaces, checks the tag out, runs `uv sync --frozen --no-dev`, restarts `golf-site`
and waits for `/healthz`. A restart takes the site down for a few seconds.

Rolling back is deploying the previous tag, which `deploy.sh` printed:

```bash
/opt/golf-site/deploy/deploy.sh v0.9.0
```

`deploy.sh` never touches `/etc`. When a release changes a file under `deploy/`, install
it again by hand as in "Setting up a server", with `sudo systemctl daemon-reload` after a
unit file and `sudo systemctl reload caddy` after the Caddyfile.

A migration moves the database forward, and an older release refuses a database newer than
it knows. Rolling back past a migration is restoring the database from before it.

## Operating

| Task | Command |
|---|---|
| Follow the site's log | `journalctl -u golf-site -f` |
| Restart after changing `/etc/golf-site/env` | `sudo systemctl restart golf-site` |
| Start again after five failed starts in five minutes, when the unit gives up | `sudo systemctl reset-failed golf-site`, then `sudo systemctl start golf-site` |
| Re-dump the holes and renders | `sudo systemctl restart golf-site` after deleting `/var/lib/golf-site/courses`, or any start whose check fails |
| Caddy's log | `journalctl -u caddy` |
| Litestream's log | `journalctl -u litestream` |

## Restoring the database

Restoring to a scratch path checks the backups without touching the live database:

```bash
sudo sh -c 'set -a; . /etc/litestream.env; litestream restore -o /tmp/restore-check.db /var/lib/golf-site/golf_site.db'
sqlite3 /tmp/restore-check.db 'PRAGMA integrity_check; SELECT count(*) FROM users;'
sqlite3 /tmp/restore-check.db 'PRAGMA integrity_check; SELECT count(*) FROM seeds;'
sudo rm /tmp/restore-check.db
```

Replacing the live database:

```bash
sudo systemctl stop golf-site litestream
sudo mv /var/lib/golf-site/golf_site.db /var/lib/golf-site/golf_site.db.broken
sudo rm -f /var/lib/golf-site/golf_site.db-wal /var/lib/golf-site/golf_site.db-shm
sudo sh -c 'set -a; . /etc/litestream.env; litestream restore -o /var/lib/golf-site/golf_site.db /var/lib/golf-site/golf_site.db'
sudo chown golf:golf /var/lib/golf-site/golf_site.db
sudo systemctl start litestream golf-site
```

`litestream restore -timestamp <RFC 3339 time>` restores the database as it was at that
time, within the snapshot retention in `deploy/litestream.yml`.

## Rebuilding a lost server

The bucket, its access key and what is kept elsewhere (the ROMs and the secrets in
`/etc/golf-site/env`) are enough to rebuild the site on a new server. A new
`GOLF_SESSION_SECRET` works, but signs everyone out.

The database must be restored before `golf-site` or Litestream first starts. `golf-site`
creates an empty database when it finds none, and Litestream would replicate that empty
database into the same bucket path as the backups.

1. Follow "Setting up a server" through "The site", up to but not including the block that
   installs the service and runs the first deploy. Point DNS at the new server.
2. Install Litestream's configuration, keys and drop-in as in "Litestream", with the same
   bucket and `path: golf-site` as before, but do not enable or start it yet:

   ```bash
   sudo cp /opt/golf-site/deploy/litestream.yml /etc/litestream.yml
   sudoedit /etc/litestream.yml
   sudo install -m 0600 /dev/null /etc/litestream.env
   sudoedit /etc/litestream.env
   sudo install -D -m 0644 /opt/golf-site/deploy/litestream-credentials.conf \
       /etc/systemd/system/litestream.service.d/credentials.conf
   sudo systemctl daemon-reload
   ```

3. Restore the database and check it:

   ```bash
   sudo sh -c 'set -a; . /etc/litestream.env; litestream restore -o /var/lib/golf-site/golf_site.db /var/lib/golf-site/golf_site.db'
   sudo chown golf:golf /var/lib/golf-site/golf_site.db
   sudo sqlite3 /var/lib/golf-site/golf_site.db 'PRAGMA integrity_check; SELECT count(*) FROM seeds;'
   ```

4. Start Litestream, then install the service and deploy the release the old server ran,
   or a newer one: an older release refuses a database newer than it knows.

   ```bash
   sudo systemctl enable --now litestream
   sudo cp /opt/golf-site/deploy/golf-site.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable golf-site
   /opt/golf-site/deploy/deploy.sh <tag>
   ```

5. Finish with "Caddy" and "Checking it".
