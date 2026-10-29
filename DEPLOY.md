# Putting CreativeFlow on a server

You need: a small Linux server (1 GB RAM is enough; any VPS such as DigitalOcean, Hetzner, AWS Lightsail),
and a domain or subdomain (for example `review.yourstudio.in`) with an A record pointing to the server's IP.
Clients get a link that starts with `https://` + your domain.

## 1. Install Docker on the server
```bash
curl -fsSL https://get.docker.com | sh
```

## 2. Copy the project and configure
Upload this folder (without `.venv`, `node_modules`, `storage`, `*.db`) to the server, then:
```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # paste into SECRET_KEY
```
Edit `.env`:
```
SECRET_KEY=<the long random value>
PUBLIC_URL=https://review.yourstudio.in
DOMAIN=review.yourstudio.in
```

## 3. Start
```bash
docker compose up -d --build
docker compose exec app flask --app app create-admin --email you@yourstudio.in --name "Your Name"
```
Open `https://review.yourstudio.in`, sign in, then fill **Settings** (studio name, phone, address, UPI ID, payee name, logo).
Do not run `seed` or `seed-showcase` on the server: they load demo data.

## 4. Backups (do this)
Everything lives in the `data` volume (database + uploaded files):
```bash
docker run --rm -v creativeflow_data:/data -v "$PWD":/out alpine tar czf /out/backup-$(date +%F).tgz -C /data .
```
Run it daily with cron and copy the file off the server.

## Updating later
Upload the new code, then `docker compose up -d --build`. Existing data is migrated automatically.

## Notes
- Email is not configured, so messages are only logged. WhatsApp links are the real channel.
- The advance is a reminder, not a lock: clients can still view previews before paying.
