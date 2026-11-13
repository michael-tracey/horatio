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
| `custodian.sh` | Makes an account the custodian, or with `--remove` stops it being one |
| `import-influence-log.sh` | Imports a troupe's influence log from the old spreadsheet |

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
   fill it in. The sample is blank. The notes above each setting say what it's
   for, where to get the value and what to watch out for.
   - **Required:** `HORATIO_DB_PASSWORD`, `HORATIO_PUBLIC_URL` (here
     `https://horatio.lotslarp.org`) and `HORATIO_LETSENCRYPT_EMAIL`. `deploy.sh`
     stops if any of them is empty. Never change the database password after the
     first deploy.
   - **Optional:** email (SMTP) and Discord stay off until their settings are
     filled in. The sample walks through making the Discord app and bot, including
     the OAuth2 redirect to register (`<HORATIO_PUBLIC_URL>/api/discord/callback`).
     The custodian manual has the same steps: [Setting up Discord and
     email](../docs/manual/custodian.md#setting-up-discord-and-email).
   - `HORATIO_PUBLIC_URL` must name the same host as `domain` in `playbook.yml`.

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

## Compression and caching

nginx gzips the app's text responses (`nginx-horatio.conf.j2`): JSON, JavaScript,
CSS, SVG and the manifest, from 1 KB up. The app itself never compresses. A troupe's
rules catalogue goes from about 590 KB to 67 KB, and the built frontend's scripts
and styles from 2.8 MB to 0.8 MB. Ubuntu 22.04's nginx has no Brotli module, so it
is gzip only. To check it, after a deploy:

```bash
curl -s -o /dev/null -D - -w 'on the wire: %{size_download} bytes\n' \
  -H 'Accept-Encoding: gzip' https://horatio.lotslarp.org/sw.js
```

It shows `content-encoding: gzip`. (Use GET, as here: the app answers `curl -I`'s
HEAD with 405. The rules catalogue needs a signed-in session, so it answers a bare
curl with a short 401, too small to compress.)

**BREACH**, an attack that reads a secret out of a compressed HTTPS response by
having the victim's browser make the same request many times with guesses in it,
needs a response that carries both a secret and something the attacker put there.
Horatio has none it can use:

- the session token is only ever in a `Set-Cookie` header, which gzip does not touch,
  and there is no CSRF token: the app relies on the `X-Horatio` header instead;
- the links with a secret in them (a new password reset link, an NPC's claim link,
  a calendar link, a Discord invite) are made by POSTs, which another site cannot
  send with the `X-Horatio` header, and reset and claim links are shown only then;
- the one GET with a secret, `/api/calendar/links`, holds nothing but the two links;
- and the session cookie is `SameSite=Lax`, so another site's requests for the API
  are made signed out.

The built frontend's files under `/assets/` have the build's hash in their names,
so the app sends them with `Cache-Control: public, max-age=31536000, immutable`.
`index.html`, the service worker and the other files that keep their names from
build to build get `no-cache`: the browser checks each time, and nginx answers 304
when the file has not changed.

The rules catalogue, the rules browser and the equipment rules
(`/api/rules/{splat}`, `/api/rules/{splat}/browse`, `/api/rules/{splat}/equipment`)
come with `Cache-Control: private, no-cache` and an ETag of the rules' version
(`horatio.api.etags`, #643). The browser keeps them and asks each time with
`If-None-Match`; nginx passes that to the app, and the app answers 304, with no
body, while the rules hold. The ETag is weak (`W/"..."`): nginx 1.18 turns a strong
ETag weak when it gzips the answer (checked in a throwaway `nginx:1.18` container with
this config), and leaves a weak one as it is. To check it, signed in (copy the
session cookie from the browser):

```bash
curl -s -o /dev/null -D - -H 'Accept-Encoding: gzip' -b 'horatio_session=…' \
  https://horatio.lotslarp.org/api/rules/vampire
```

It shows `etag: W/"…"`; the same with `-H 'If-None-Match: W/"…"'` gives 304.

## What is live

**Custodian → System** shows the commit the running image was built from (linked to
GitHub, and marked if uncommitted changes went in), when it was built, when the app
last started, and whether the database is on the newest migration that build has.
`deploy.sh` bakes the commit and build time into the image; a `--no-build` redeploy
keeps the image's own.

## Importing the influence log

LotsLarp's influence history is in the `Elite Infl.` and `UW Infl.` tabs of its old
spreadsheet. Download the spreadsheet as .xlsx (File → Download → Microsoft Excel),
or those two tabs as CSV into one folder, then:

```bash
deploy/import-influence-log.sh LotsLarp.xlsx --troupe "LotsLarp" --dry-run  # see what it would do
deploy/import-influence-log.sh LotsLarp.xlsx --troupe "LotsLarp"
```

It reports the rows it skipped and why, and the names that match no character in
the troupe, which it keeps as text. Running it again updates the entries it made
rather than adding them twice, so once the characters are in Horatio, run it again
to link their entries. Dates are midnight in `--timezone`, `America/New_York` unless
given.

## Importing characters from Yorick

A troupe's characters come across from Yorick in the app: the custodian uploads the
troupe's **Print Characters** page under **Custodian › Import from Yorick**
(`docs/manual/custodian.md`, "Importing characters from Yorick"). The page is kept
under the upload directory (`/uploads/yorick-imports/`, never served) until it is
imported, deleted, or 30 days old. nginx lets that one upload be up to 50 MB. The
import makes a backup in the server's backup directory first, as **Back up now** does.

## Dark Pack resources

The Dark Pack logo (About page) and the clans' symbols (game badges) come from
Paradox's free Dark Pack kit, which Horatio never ships. The custodian fetches them
on the server in **Custodian › Tools › Dark Pack resources**, which downloads the
kit (about 450 MB) and keeps only what Horatio uses in
`/opt/docker-apps/horatio/dark-pack`. The app container mounts that folder
read-write as `HORATIO_DARK_PACK_DIR`; the playbook creates it, owned by the app's
user, and never copies anything into it, so deploys leave it alone. A fetch needs
about 1 GB free there while it runs: the download, and the two zips inside it.
**Custodian › Tools › VTES symbols** keeps KRCG's VTES symbols in its `vtes/`
folder. Without either the app runs as before, minus the logo and symbols. The
nightly backup packs up the folder too ([Backups](#backups)).

Before #534, `deploy.sh` copied the deploying machine's `dark-pack/` there on every
deploy and the app mounted it read-only. What those deploys copied stays and keeps
working, with nothing to import again; the first deploy after makes the folder the
app's own, so the Tools tab can replace or remove it.

## Backups

Every night at 03:17 (host time), `/opt/docker-apps/horatio/backup.sh`:

- dumps the database
- packs up the uploaded pictures (`/opt/docker-apps/horatio/uploads`, mounted in the
  app as `HORATIO_UPLOAD_DIR`) as `horatio-uploads-<time>.tar.gz`
- packs up the Dark Pack folder (`/opt/docker-apps/horatio/dark-pack`, with the VTES
  symbols in `vtes/`) as `horatio-dark-pack-<time>.tar.gz`, a few MB. It leaves out
  the folders a fetch works in, so one taken during a fetch holds only finished sets,
  and is skipped while the folder is missing or empty
- uploads them to `gs://lotslarp-horatio-backups`, which deletes copies after 30 days
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

Pictures are restored from the night's `horatio-uploads-<time>.tar.gz` beside it:

```bash
sudo tar -xzf horatio-uploads-YYYYMMDDTHHMMSSZ.tar.gz -C /opt/docker-apps/horatio
sudo chown -R 10001 /opt/docker-apps/horatio/uploads
```

The Dark Pack resources and VTES symbols from `horatio-dark-pack-<time>.tar.gz`, if
there is one (they can also be fetched again in **Custodian › Tools**). Move the
folder aside first, so nothing fetched since stays mixed in:

```bash
sudo mv /opt/docker-apps/horatio/dark-pack /opt/docker-apps/horatio/dark-pack.before
sudo tar -xzf horatio-dark-pack-YYYYMMDDTHHMMSSZ.tar.gz -C /opt/docker-apps/horatio
sudo chown -R 10001 /opt/docker-apps/horatio/dark-pack
```

The app needs no restart: **Custodian › Tools** reads the restored sets back. Remove
`dark-pack.before` once they look right.

A backup from the bucket: `gcloud storage cp gs://lotslarp-horatio-backups/<name> .`.
