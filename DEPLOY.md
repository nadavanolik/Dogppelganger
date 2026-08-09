# Deployment (CI/CD)

This project ships as **three containers** — `site` (React SPA + nginx),
`model` (Flask API), and `db` (Postgres) — wired together by
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

### 1. Generate a **deploy key** for GitHub → VM

Your personal SSH key lets *you* log into the VM. GitHub Actions needs its
**own** key. On your laptop:

```bash
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/dogppelganger_deploy
```

This makes two files:

- `dogppelganger_deploy` (private) → goes into a GitHub secret
- `dogppelganger_deploy.pub` (public) → goes onto the VM

### 2. Prepare the VM

SSH into the VM (with your personal key) and run:

```bash
# Install Docker + compose plugin (Ubuntu/Debian)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER      # then log out & back in

# Let the GitHub deploy key log in
cat >> ~/.ssh/authorized_keys      # paste the CONTENTS of dogppelganger_deploy.pub, then Ctrl-D

# Clone the repo (public repo → no auth needed)
git clone https://github.com/nadavanolik/Dogppelganger.git ~/dogppelganger
cd ~/dogppelganger

# Create the production secrets file (see .env.example)
cp .env.example .env
nano .env    # set SECRET_KEY + a real POSTGRES_PASSWORD
```

### 3. Make the GHCR images pullable

The simplest option for a student project: after the **first** successful
deploy, open each package at
`https://github.com/nadavanolik?tab=packages`
(`dogppelganger-site`, `dogppelganger-model`) → **Package settings** →
**Change visibility → Public**. Then the VM pulls with no login.

> Private alternative: run `docker login ghcr.io` on the VM with a Personal
> Access Token that has `read:packages`, and add that step to the deploy script.

### 4. Add the GitHub repository secrets

Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret            | Value                                                        |
| ----------------- | ----------------------------------------------------------- |
| `SSH_HOST`        | the VM's IP or hostname                                      |
| `SSH_USER`        | your VM username (e.g. `ubuntu`)                            |
| `SSH_PRIVATE_KEY` | the **entire** contents of `~/.ssh/dogppelganger_deploy`    |

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
# terminal 1 — Flask API on :5000 (uses a local SQLite file, no Postgres needed)
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

- `backend/website/model.py` is a **placeholder** matcher. Swap `predict_breed`
  for the real ML model — the API contract in `views.py` won't change.
- HTTPS: put a real domain + TLS (e.g. Caddy or nginx + certbot) in front later.
  For now the site is served over plain HTTP on port 80.
