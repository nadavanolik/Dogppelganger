# Deployment (CI/CD)

This project ships as **three containers** — `site` (React SPA + nginx),
`model` (FastAPI), and `db` (Postgres) — wired together by
`docker-compose.yml`.

## How the pipeline works

```
git push main
   │
   ├─▶ CI  (.github/workflows/ci.yml)  ── lint • typecheck • build • py_compile
   │
   └─▶ CD  (.github/workflows/deploy.yml)
          │  1. build the two images
          │  2. push them to GHCR (GitHub Container Registry)
          │  3. SSH into the VM ─▶ git pull • docker compose pull • up -d
          ▼
        VM runs the new containers
```

You (locally) push → GitHub builds the images → GitHub logs into the VM and
restarts the stack with the fresh images. The VM never builds anything; it just
pulls prebuilt images, so it stays fast even if it's a small machine.

---

## One-time setup

You only do this once, after your teacher gives you VM access.

### 1. The SSH key for GitHub → VM

GitHub Actions logs into the VM over SSH, so it needs a private key that the VM
trusts.

- **If you already have a key dedicated to this VM** (public key handed to whoever
  provisioned the VM): reuse it. Its **private** key goes into a GitHub secret in
  step 4 — nothing else to generate.
- **Otherwise**, make one and put its public half on the VM:

  ```bash
  ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/dogppelganger_deploy
  cat ~/.ssh/dogppelganger_deploy.pub   # append this to the VM's ~/.ssh/authorized_keys
  ```

> The private key must be in **OpenSSH format** (starts with
> `-----BEGIN OPENSSH PRIVATE KEY-----`). If yours is a PuTTY `.ppk`, export it as
> OpenSSH first (PuTTYgen → Conversions → Export OpenSSH key).

### 2. Open port 80 (Azure)

Azure VMs allow only SSH (22) inbound by default, so the site would be
unreachable on port 80. In the Azure Portal:

**VM → Networking → Network settings → Add inbound port rule** → Destination port
`80`, Protocol TCP, Action Allow. (Add `443` too if you set up HTTPS later.)

### 3. Prepare the VM

SSH into the VM with your key and run:

```bash
ssh -i /path/to/your_private_key <vm-user>@<vm-public-ip>

# Install Docker + compose plugin (Ubuntu/Debian)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER      # then log out & back in

# If you generated a SEPARATE deploy key, add its public half now:
# cat >> ~/.ssh/authorized_keys    # paste dogppelganger_deploy.pub, then Ctrl-D

# Clone the repo (public repo → no auth needed)
git clone https://github.com/nadavanolik/Dogppelganger.git ~/dogppelganger
cd ~/dogppelganger

# Create the production secrets file (see .env.example)
cp .env.example .env
nano .env    # set SECRET_KEY + a real POSTGRES_PASSWORD
```

⚠️ **`SECRET_KEY` is no longer optional.** It signs every login token, so a
placeholder value means anyone who can read this repo can mint a token for any
account. The app now refuses to start against Postgres if it is left at a known
default. Generate one with:

```bash
openssl rand -hex 32
```

Changing it later logs everybody out (their tokens no longer verify), which is
inconvenient but not dangerous.

### 4. Make the GHCR images pullable

The simplest option for a student project: after the **first** successful
deploy, open each package at
`https://github.com/nadavanolik?tab=packages`
(`dogppelganger-site`, `dogppelganger-model`) → **Package settings** →
**Change visibility → Public**. Then the VM pulls with no login.

> Private alternative: run `docker login ghcr.io` on the VM with a Personal
> Access Token that has `read:packages`, and add that step to the deploy script.

### 5. Add the GitHub repository secrets

Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret            | Value                                                          |
| ----------------- | -------------------------------------------------------------- |
| `SSH_HOST`        | the VM's **public IP** (Azure Portal → VM overview)            |
| `SSH_USER`        | the VM admin username you set when creating it (e.g. `azureuser`) |
| `SSH_PRIVATE_KEY` | the **entire** contents of your private key file, incl. the header/footer lines |

`GITHUB_TOKEN` (used to push images to GHCR) is provided automatically — you
don't create it.

---

## First deploy

Push to `main` (or use the **Actions → Deploy → Run workflow** button). Watch it
in the **Actions** tab. When it finishes, the site is live at the VM's address:

```
http://<SSH_HOST>/
```

Quick checks:

```bash
curl http://<SSH_HOST>/api/health      # -> {"status":"ok"}
```

### Database schema

The deploy workflow now runs `scripts/migrate_schema.py` on the VM before
starting the new containers. You don't need to do anything — it's idempotent
and prints `nothing to do` once applied.

It's there because `create_all()` only ever creates *missing tables*: it never
adds a column to a table that already exists, and `dbdata` is a named volume
that survives every deploy. Without it, a VM running the old schema would 500
on every upload, forum and match request at once. To inspect the plan by hand:

```bash
cd ~/dogppelganger && docker compose run --rm model python scripts/migrate_schema.py --dry-run
```

#### One-time reset when real users land

`migrate_schema.py` can add and drop columns; it cannot turn a `VARCHAR(64)`
holding `"u_moodyoak"` into an integer foreign key, because no `USING`
expression exists for that. So the change that makes users real ships with a
deliberate wipe. The full sequence is in **[Releasing the real-users
change](#releasing-the-real-users-change)** below — do not run it standalone
without reading that, because the order matters.

It needs both `--yes` and `ALLOW_DB_RESET=1`, prints what it will destroy, and
leaves the dog corpus alone — **both the files and the `dog_assets` /
`calibrations` rows**, which hold no user data and would otherwise cost the
700 MB archive plus the embedding and calibration passes to rebuild. It is
**not** in `deploy.yml` on purpose: a destructive step must never run on every
push.

⚠️ Do **not** use `docker compose down -v` for this. That removes `dogdata` too,
and re-ingesting the corpus is a 226 MB download and a long pass.

---

## Releasing the real-users change

Read this end to end before starting. There is a window where the site is down,
and the order is what keeps it short.

### Why there is a window at all

Pushing to `main` triggers the deploy automatically: it builds the images, SSHes
in, runs `migrate_schema.py`, and restarts. But `migrate_schema.py` cannot make
this particular change, so it will report "nothing to do" and the new code will
come up against the **old schema** — where `owner_id` is still a `VARCHAR`.
Postgres will reject the queries and the API will error until the reset is run.

So the reset is not optional cleanup. It is part of the release, and it happens
within a minute or two of the merge.

### 0. Before you merge anything

The VM is not on all the time. Start it, then:

```bash
ssh vmadmin@52.188.127.173
cd ~/dogppelganger
cat .env 2>/dev/null || echo "no .env — running on compose defaults"
```

⚠️ **If `SECRET_KEY` is missing or a placeholder, fix it now.** The new backend
refuses to start against Postgres with a known default value, so the `model`
container will crash-loop and the reset in step 3 will have nothing to run in.
A deployment with no `.env` at all has been running on `SECRET_KEY=change-me`,
which is one of the values it will refuse.

⚠️ **Do not copy `.env.example` verbatim.** Its `POSTGRES_PASSWORD` is a
placeholder, and Postgres only reads that variable when it *first* initialises
its data directory. On a server that has already run, the `dbdata` volume keeps
the original password, so a new value here only makes the API build a connection
string the database rejects. Find out what is actually in use and match it:

```bash
docker compose exec model printenv DATABASE_URL   # authoritative — it works today
```

Then write the file, changing only the signing key:

```bash
cat > .env <<'EOF'
SECRET_KEY=REPLACE_ME
POSTGRES_USER=dogapp
POSTGRES_PASSWORD=dogapp
POSTGRES_DB=dogppelganger
EOF
sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$(openssl rand -hex 32)|" .env

docker compose up -d && curl -s localhost/api/health
```

Rotating the signing key logs out everyone currently signed in, which does not
matter here — step 3 deletes the accounts anyway.

### 1. Fix the build pipeline first, on its own

Deploys have been failing since the GHA build cache was added to the model step:
`build-push-action` was using the default `docker` driver, which cannot export
cache, so buildx died before building anything. `docker/setup-buildx-action` is
the fix.

Land that **before** the feature merge, and let it deploy on its own. You want
to know the pipeline is healthy before you also change the schema — otherwise a
red deploy has two possible causes and you're debugging both at once.

### 2. Merge the feature

Open a PR from `feat/real-users` into `main` (this is also the first time the
branch gets CI, which runs lint, typecheck, build and the 284 tests), then
merge. The deploy fires automatically. Expect the site to be broken from the
moment the containers restart until step 3 completes.

### 3. Reset, immediately

```bash
ssh vmadmin@52.188.127.173
cd ~/dogppelganger
docker compose run --rm -e ALLOW_DB_RESET=1 model python scripts/reset_db.py --yes
docker compose up -d
```

Every account, photo, post, message and leaderboard entry is gone; the dog
corpus is untouched, so matching still works. The forum re-seeds itself with
three demo accounts on the next start.

### 4. Check it

```bash
curl -s http://52.188.127.173/api/health
curl -s http://52.188.127.173/api/gallery | head -c 200   # public, no auth
```

Then in a browser: sign up, upload a photo (over 1 MB — that path was broken
before this release), share the match, open the gallery logged out, and send
yourself a DM from a second account in a private window.

### 5. What is deliberately not automated

- The reset. Destructive and one-time.
- Turning the VM on. It is off by default and that is intentional.
- HEIC photo support and the remaining follow-ups in `MIGRATION.md`.

### Seed the dog corpus (once, after the first deploy)

Matching has nothing to match against until the AFHQ dog photos are on the
`dogdata` volume, and every dog image on the site 404s. This is a **one-time**
step — the volume is named, so deploys never touch it.

Copy the extracted dog folder up, then run the ingest inside the backend
container:

```bash
scp -r ~/Downloads/afhq <SSH_USER>@<SSH_HOST>:~/afhq
```

```bash
cd ~/dogppelganger && docker compose run --rm -v ~/afhq:/seed:ro model python scripts/ingest_dogs.py --source /seed
```

It takes a few minutes for 5,239 images and is safe to interrupt and re-run.

### Embed the corpus and calibrate (once, straight after seeding)

Matching needs vectors, not just pixels. Both passes use the ONNX encoder that
is already baked into the image, so neither needs PyTorch on the VM.

```bash
cd ~/dogppelganger && docker compose run --rm model python scripts/embed_dogs.py
```

Then the human reference statistics — any folder of face photos works; LFW is
a convenient, freely available one. The images are read and discarded, and only
aggregate statistics are stored:

```bash
curl -L -o lfw.tgz https://ndownloader.figshare.com/files/5976018 && tar xzf lfw.tgz
```

> That figshare address is a mirror of Labeled Faces in the Wild. The original UMass
> host (`vis-www.cs.umass.edu`) no longer resolves. Any folder of face photos
> works — LFW is only a convenient, freely available default.

```bash
cd ~/dogppelganger && docker compose run --rm -v ~/lfw:/faces:ro model python scripts/calibrate_humans.py --source /faces
```

Confirm the whole thing worked:

```bash
curl http://<SSH_HOST>/api/dogs/stats     # -> {"total":5239,"embedded":5239,...}
```

`total: 0` means the corpus is still empty; `embedded: 0` means it has pixels
but no vectors and every match will fail with a message saying so. See
`DATA_STORAGE.md` §5 and §7 for the full contracts.

On the VM you can inspect things with:

```bash
cd ~/dogppelganger
docker compose ps
docker compose logs -f model
```

---

## Running locally

**Whole stack in Docker (closest to production):**

```bash
docker compose up --build
# site  -> http://localhost/
# api   -> http://localhost/api/health
```

**Frontend and backend separately (fastest for development):**

```bash
# terminal 1 — FastAPI on :5001 (uses a local SQLite file, no Postgres needed)
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py

# terminal 2 — React dev server on :5173 (proxies /api to :5001)
npm install
npm run dev
```

> **Why 5001 and not 5000.** On macOS, AirPlay Receiver (ControlCenter) has
> listened on 5000 since Monterey and answers every request with `403` — which
> surfaces in the browser as "Request failed (403)" on upload and looks exactly
> like a broken backend. Both dev defaults are therefore 5001 and no environment
> variables are needed. Override with `PORT` and `API_PORT` if you move it; keep
> the two in step. Docker is unaffected: nginx talks to `model:5000` on the
> container network, where nothing else is listening.

Matching needs the corpus before it will do anything locally: `ingest_dogs.py`,
then `embed_dogs.py`, then `calibrate_humans.py` — `DATA_STORAGE.md` §5 and
§7.4. `curl localhost:5001/api/dogs/stats` tells you where you are.

---

## Notes / future work

- Matching is CLIP retrieval with species-mean centring and a shared text
  attribute space (`backend/app/ml`, `DATA_STORAGE.md` §7). PyTorch is not in
  the runtime image: the encoder is exported to ONNX in a discarded Docker
  build stage, so the container carries the model without the framework.
- HTTPS: put a real domain + TLS (e.g. Caddy or nginx + certbot) in front later.
  For now the site is served over plain HTTP on port 80.
