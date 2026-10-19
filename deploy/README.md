# Deploying Horatio

Horatio runs at **https://horatio.lotslarp.org** on the shared GCE docker host
(`docker-host`, from the `infra` repo), beside codex-mysterium's API and the
lotslarp Discord bot. It deploys the way they do: Cloud Build builds the image
into Artifact Registry in the `lotslarp` project, and an Ansible playbook runs it
on the host.

```
             horatio.lotslarp.org  (DNS only, not proxied by Cloudflare)
                        │
host nginx :443 ── Let's Encrypt certificate, renewed by certbot's timer
                        │
       horatio-api  127.0.0.1:8100   the app, serving the built frontend too
                        │   docker network "horatio"
       horatio-db   Postgres 18      data in /opt/docker-apps/horatio/postgres
```

| File | What it does |
|---|---|
| `../Dockerfile` | One image: builds the frontend, serves it from the API |
| `cloudbuild.yaml` | Builds and pushes the image (what is uploaded: `../.gcloudignore`) |
| `deploy.sh` | Builds, then runs `playbook.yml` against the host |
| `playbook.yml` | Postgres, migrations, the app, nginx and TLS, nightly backups |
| `production.env.example` | The settings to copy to `production.env` (gitignored) |
| `custodian.sh` | Makes an account the custodian |

## Before the first deploy

1. **Infra** (the `infra` repo, `terraform/horatio.tf`): the Artifact Registry
   repository, the backup bucket and the DNS record for `horatio.lotslarp.org`.
   Apply it there with `tofu apply`, and wait for the name to resolve to the host
   (`dig +short horatio.lotslarp.org`). Let's Encrypt checks it over HTTP.
2. **Tools** on the deploying machine: `gcloud` (signed in, with access to the
   `lotslarp` project), `jq`, `ansible` with the `community.docker` collection,
   and the host's SSH key at `~/.ssh/ansible_gce_key`. These are the same tools as for
   the other apps.
3. **Settings:** `cp deploy/production.env.example deploy/production.env` and
   fill it in:
   - `HORATIO_DB_PASSWORD`: `openssl rand -hex 24`. Postgres keeps the password
     it was created with, so never change it afterwards.
   - `HORATIO_LETSENCRYPT_EMAIL`: where certificate expiry warnings go.
   - Discord and SMTP: optional; each connector stays off until its settings are
     filled in. For Discord, also register
     `https://horatio.lotslarp.org/api/discord/callback` as an OAuth2 redirect.

## Deploying

```bash
deploy/deploy.sh             # build the current checkout and deploy it
deploy/deploy.sh --no-build  # redeploy the latest image, e.g. after changing settings
```

A deploy:

1. builds and pushes the image, tagged with the commit and time;
2. writes the settings to the host (`/opt/docker-apps/horatio/app.env`, mode 600);
3. starts Postgres if it is not running;
4. migrates the database and reloads the rules in a one-off container. If this
   fails, the deploy stops and the running app is untouched;
5. replaces the app container and waits for `/api/health`;
6. on the first deploy, gets the TLS certificate; after that, certbot renews it;
7. installs the nightly backup, and keeps the newest 5 images in Artifact
   Registry.

The first time, sign up on the site, then make yourself the custodian:

```bash
deploy/custodian.sh you@example.com
```

## Looking at it

```bash
ssh -i ~/.ssh/ansible_gce_key ansible@<host-ip>      # the IP: infra repo, `tofu output host_ip`
docker ps --filter name=horatio
docker logs --tail 100 horatio-api                   # also in Cloud Logging (gcplogs)
docker exec -it horatio-db psql -U horatio horatio
```

## Backups

Every night at 03:17 (host time), `/opt/docker-apps/horatio/backup.sh`:

- dumps the database
- uploads it to `gs://lotslarp-horatio-backups`, which deletes copies after 30 days
- keeps the last week in `/opt/docker-apps/horatio/backups`

Its log is `/var/log/horatio-backup.log`.

The custodian can also make a backup and download any kept one in the app, under
**Custodian → Backups**. Those are named `horatio-<time>-manual.sql.gz`, kept beside the
nightly ones (the app container mounts the directory as `HORATIO_BACKUP_DIR`) and
pruned after a week the same way. Only the nightly ones go to the bucket. From the
host, `sudo /opt/docker-apps/horatio/backup.sh` takes a nightly-style backup now.

To restore one, stop the app, recreate the database and load the dump:

```bash
docker stop horatio-api
docker exec horatio-db dropdb -U horatio horatio
docker exec horatio-db createdb -U horatio horatio
gunzip -c horatio-YYYYMMDDTHHMMSSZ.sql.gz | docker exec -i horatio-db psql -U horatio horatio
docker start horatio-api
```

A backup from the bucket: `gcloud storage cp gs://lotslarp-horatio-backups/<name> .`.
