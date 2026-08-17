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
Confirm it worked:

```bash
curl http://<SSH_HOST>/api/dogs/stats     # -> {"total":5239,...}
```

`total: 0` means the corpus is still empty. See `DATA_STORAGE.md` §5 for the
full ingest contract.

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
# terminal 1 — FastAPI on :5000 (uses a local SQLite file, no Postgres needed)
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py

# terminal 2 — React dev server on :5173 (proxies /api to :5000)
npm install
npm run dev
```

---

## Notes / future work

- `backend/app/model.py` is a **placeholder** matcher. Swap `predict_breed`
  for the real ML model — the API contract in `views.py` won't change.
- HTTPS: put a real domain + TLS (e.g. Caddy or nginx + certbot) in front later.
  For now the site is served over plain HTTP on port 80.
