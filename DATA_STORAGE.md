# Data storage & the matching model — working guideline

**Owner:** Ilona · **Scope:** where every byte and every row lives, and the seam the
matching model plugs into. This is the document to read before touching
`backend/app/storage/`, `backend/app/models.py`, or `backend/scripts/`.

Read `MIGRATION.md` first if you don't know the current shape of the repo.

---

## 1. What problem this solves

Before this work, `src/lib/dogImages.json` listed **5,239 AFHQ filenames** and
`src/lib/dogSrc.ts` built `/dogs/<filename>` URLs — but `public/dogs/` was
**empty**. Every dog picture on the site was a 404, and `backend/app/model.py`
answered every match with a SHA-256 hash of the filename mapped onto eight
hardcoded breed names.

So there are three jobs, in order:

1. **Store the dog corpus** so the site can actually show a dog. (§2-5)
2. **Store user photos** safely, and the human↔dog pair each match produces. (§3-4)
3. **Replace the hash stub** with real retrieval over the corpus. (§7)

All three are done. What remains is judgement, not code: nobody has yet run the
pipeline over the real AFHQ corpus and looked at whether the dogs resemble the
people — see §7.6.

---

## 2. Decisions, and why

### 2.1 One database: PostgreSQL

MongoDB was considered and rejected. `main` already runs SQLAlchemy 2.0 +
Postgres with a green pytest suite covering the game engine, the forum and the
upload queue. Migrating that to Mongo would rewrite ~1,000 lines of working code
for no capability we need: the data here is relational (a match *references* a
dog, a job *belongs to* an owner), and the one thing Mongo would have bought us
— GridFS for blobs — is a worse fit than the filesystem for 5,239 immutable
public JPEGs. `ProjectPlan.md` §1 stays accurate.

**Consequence:** vectors live as raw `float32` bytes in a `LargeBinary` column,
not in `pgvector` or a Mongo vector index. See §4.2 for why that is not a
compromise at this corpus size.

### 2.2 Image bytes on a Docker volume, never in the database

| | Dog corpus | User uploads |
|---|---|---|
| Volume | `dogdata` | `appdata` (the existing `gamedata`) |
| Mounted into `model` | `/data/dogs` **rw** | `/app/data/uploads` **rw** |
| Mounted into `site` | `/usr/share/nginx/html/dogs` **ro** | — not mounted — |
| Served by | **nginx, directly** | **FastAPI, after an ownership check** |
| Cache header | `public, max-age=31536000, immutable` | `private, no-store` |

The split is deliberate and is the single most important thing on this page:

- **Dog photos are public, immutable and hot.** Putting them behind Python would
  burn a worker on every thumbnail. nginx already serves `/dogs/*` and
  `dogSrc.ts` already builds exactly those URLs, so serving them from a
  read-only mount required *no frontend change at all*.
- **User photos are personal data.** They must never be reachable by guessing a
  URL, so every read goes through `/api/uploads/{job_id}/image`, which checks
  the requesting owner. That endpoint is slower, and that is the correct
  trade-off.

Blobs stay out of Postgres because 226 MB of JPEGs in `bytea` bloats every
backup, every `pg_dump`, and the shared buffer cache, to replace a job the
kernel page cache already does better.

### 2.3 Forum posts, comments, reactions, DMs: same Postgres

Yes — one database for the whole app. `posts`, `comments` and `reactions`
already live there. Forum *media* (images and video) will follow the user-upload
pattern in §2.2: bytes on the `appdata` volume, a row in Postgres pointing at
them, served through an authorising endpoint. Caps in §6.

### 2.4 No breed names

AFHQ has no breed labels. Everything that claimed one — `Match.breed_name`,
`UploadJob.breed_name`, `.trait`, the eight-breed list in `model.py`, and the
`breedName`/`trait` fields in the API — was inventing them, and an invented
"Golden Retriever" over a photo of a pug is a visible bug worth −5 points.

They are replaced by an honest reference to the dog that was actually retrieved:

```
breed_name, trait, confidence   →   dog_asset_id, score, shared_traits
```

`shared_traits` is the *explanation* — the attributes the person and the dog
scored alike on ("fluffy", "sleepy eyes", "long face"), computed by the
attribute bridge in §7.

---

## 3. On-disk layout

```
dogdata volume
├── 512/flickr_dog_000002.jpg     archival · JPEG q90 · EXIF stripped
├── 256/flickr_dog_000002.webp    display  · WebP q82   ~15 KB
└── 128/flickr_dog_000002.webp    thumb / game tile · WebP q80  ~5 KB

appdata volume  (/app/data)
├── game/                         existing leaderboard snapshots — untouched
├── uploads/0000/                 sharded by job_id // 1000
│   ├── 17-orig.jpg               re-encoded original, ≤ 1024 px
│   ├── 17-display.webp           512 px
│   └── 17-thumb.webp             256 px
└── attachments/0000/             sharded by message_id // 1000
    ├── 42-display.webp           512 px — images only
    ├── 42-thumb.webp             256 px — images only
    └── 43-orig.mp4               video, exactly as received
```

Uploads and attachments are sharded because a single directory holding tens of
thousands of entries degrades on ext4. `id // 1000` keeps ~3,000 files per
directory and, unlike hashing the owner id, puts nothing user-identifying in a
path.

An image attachment has **no `orig`**: nothing runs a model over a chat photo,
so keeping a full-resolution copy would be pure disk cost. A video has no
derivatives, because generating one would mean decoding it (see §6).

In both cases the path is a pure function of the row id and content type — there
is deliberately no path column, so the database and the disk cannot disagree.

**Disk pressure to watch.** Attachments share the volume with uploads and the
leaderboard snapshot. Two hundred clips at the 25 MB cap is 5 GB, and a full
disk takes Postgres down with it, not just attachments. `docker system df -v`
before a demo. A per-user quota is the obvious next control and is deliberately
not built yet.

Total for the dog corpus: **~226 MB** at 512 px + ~79 MB WebP + ~25 MB thumbs
≈ **330 MB**. It is seeded once and then survives deploys exactly like `dbdata`
does — `docker compose up -d` never touches a named volume.

---

## 4. Schema

### 4.1 `dog_assets` — the corpus

| column | type | note |
|---|---|---|
| `id` | int PK | internal |
| `slug` | str, unique | `flickr_dog_000002` — stable public name |
| `filename` | str, unique | what nginx serves out of `512/` |
| `checksum` | str(64), indexed | SHA-256 of the **original** bytes — integrity + duplicate detection. Not unique, see §5.2 |
| `source_split` | str | `train` / `val`, kept for provenance |
| `width`, `height`, `byte_size` | int | of the archival derivative |
| `manifest_index` | int, unique | position in `src/lib/dogImages.json` — see §5.3 |
| `embedding` | bytes | `float32` vector, `np.ndarray.tobytes()`; NULL until `embed_dogs.py` runs |
| `embedding_dim`, `embedding_model` | int, str | so a model swap invalidates cleanly |
| `attributes`, `attribute_set` | bytes, str | the attribute vector behind `shared_traits` (§7.1) |

### 4.1b `calibrations` — the human side

One row: the mean CLIP embedding of a reference set of human faces, plus the
mean and standard deviation of their attribute scores. This is what §7.1's
centring subtracts and what the attribute z-scores divide by.

Only the human side is stored. Dog statistics are derived from the corpus at
load time so they cannot describe a different set of vectors than the ones they
are applied to; the human side has no such source, so it is computed once by
`scripts/calibrate_humans.py`. `model` and `attribute_set` are part of the
unique key — statistics from one encoder are meaningless applied to another's
vectors, and the mismatch must be detectable rather than silently wrong.

### 4.2 Why raw bytes instead of a vector index

CLIP ViT-B/32 gives 512 dimensions. 5,239 dogs × 512 × 4 B = **10.7 MB** — the
entire corpus of embeddings fits in RAM with room to spare. At startup the
service loads them into one `(5239, 512)` numpy array; a match is then a single
matrix-vector product, on the order of a millisecond. FAISS, pgvector and Atlas
Vector Search all exist to avoid a linear scan that, at this size, is already
faster than the index lookup would be. Adding one would be architecture theatre.

`embedding_model` and `embedding_dim` are stored per row so that changing the
model is detectable: the loader refuses to build a matrix out of rows tagged
with a different model rather than silently mixing vector spaces.

### 4.3 Changes to existing tables

`UploadJob` and `Match` both lose `breed_name` / `trait` / `confidence` and gain
`dog_asset_id` (FK), `score`, `shared_traits`. `UploadJob` additionally records
what was actually stored — `checksum`, `byte_size`, `width`, `height` — because
the queue's shortest-job-first ordering needs a real size, not the multipart
header's claim.

> `Match` and `UploadJob` now describe nearly the same thing. Consolidating them
> is a follow-up, not part of this change — `/api/match` is a live endpoint and
> collapsing the two tables is a call for the whole team, not for me alone.

### 4.3b `users`, and who owns what

Previously undocumented, and previously not really true: a `users` table existed
with bcrypt-hashed passwords, but **nothing referenced it**. Ownership was a
`VARCHAR(64)` the browser made up and the server believed. It is now a real
foreign key everywhere.

```
users(id, email UQ, username UQ, password, token_version, created_at, updated_at)
```

`token_version` is what makes changing your password mean something: every token
carries the value it was minted with, and one that disagrees with the row is
rejected. Without it a token stolen an hour ago outlives the password it was
issued against for a full day.

The foreign keys split into two groups, and the split *is* the deletion policy:

| Cascades — dies with the account | Nullable, SET NULL — survives as `[deleted user]` |
|---|---|
| `upload_jobs.owner_id` | `posts.author_id` |
| `matches.user_id` | `comments.author_id` |
| `reactions.user_id` | `messages.sender_id` |
| `notifications.user_id` | `conversations.user_a_id` / `user_b_id` |

The rule: a row that is *about* the person dies with them; a row *addressed to
other people* survives without them, because a thread other people replied to
stops making sense with holes in it. A reaction cascades rather than
anonymising for a second reason — a NULL there would defeat
`uq_reaction_target_user`, since NULLs don't collide, letting one ghost
accumulate unlimited likes on a post.

`posts.image_job_id` is `SET NULL` too, so an anonymised post keeps its words
and loses its picture. That falls out of the rules above and happens to be
exactly right.

⚠️ **The cascades are a safety net, not the mechanism.** SQLite does not enforce
`ondelete` unless `PRAGMA foreign_keys=ON`, which this project never issues — so
they fire in production Postgres and silently don't under pytest. Deletion is
therefore written out step by step in `backend/app/services/users.py`, so the
tests exercise the path production takes.

### 4.3c `conversations` and `messages` — direct messages

Two tables, not one. A single `messages(sender_id, recipient_id, …)` table where
"the conversation" is the unordered pair looks simpler until the inbox query,
which needs the latest message per pair: that means `LEAST`/`GREATEST` on
Postgres and `MIN`/`MAX` on SQLite — different function names, in the one query
that must be right, across exactly the split this project runs.

```
conversations(id, user_a_id, user_b_id, created_at, last_message_at)
    UNIQUE(user_a_id, user_b_id)   CHECK(user_a_id < user_b_id)
messages(id, conversation_id, sender_id, body, created_at, read_at,
         attachment_kind, attachment_content_type, attachment_byte_size,
         attachment_width, attachment_height, attachment_name)
    CHECK(body IS NOT NULL OR attachment_kind IS NOT NULL)
```

`user_a_id < user_b_id` is the invariant that makes the unique constraint mean
"one thread per pair" rather than "one per direction" — without it, A messaging
B and B messaging A build two half-conversations.

History is ordered and paged by **`id`, never `created_at`**: two messages
written in the same tick share a timestamp, and an ordering that can tie is an
ordering that can drop a message off the end of a page. The cursor is
`?before=<id>`.

`read_at` is per message rather than a high-water mark on the conversation: one
nullable column instead of two, correct when the same person has two tabs open,
and the inbox's unread counts come out of one grouped query.

The attachment lives in columns rather than its own table because a message
carries at most one, so a 1:1 table whose rows are always created and destroyed
with their parent would be a join pretending to be a decision.

**Offline delivery needs no mechanism**, and that is worth writing down because
it is easy to over-engineer: a message is a row before it is ever a frame. If
the recipient has no socket the push finds nothing and does nothing, and the
message is waiting in their inbox with an unread badge next time they look.

### 4.4 Migrating an existing database

`main.py` calls `Base.metadata.create_all()`, which creates **missing tables and
nothing else** — it will not add a column to a table that already exists. The
Postgres data directory is the named volume `dbdata`, which survives every
deploy. So a VM that has already run the old code keeps an `upload_jobs` table
with `breed_name`/`trait`/`confidence` and none of the new columns, and every
query the new mapping emits fails at once: uploads, the forum feed and the match
endpoints all 500 together. `matches.breed_name` was `NOT NULL`, so inserts fail
too, not just reads.

`backend/scripts/migrate_schema.py` fixes that. It inspects the live schema and
issues only the changes actually missing, so it is safe to run repeatedly and is
a no-op on a fresh database. The deploy workflow runs it on every deploy, before
`docker compose up -d`; run it by hand with `--dry-run` first if you want to see
the plan.

It is deliberately not Alembic — one schema change across two tables does not
justify a migration framework with a version history. If the schema starts
moving regularly, switch to Alembic rather than growing that script.

⚠️ **The real-users change could not use it.** Turning `owner_id` from
`VARCHAR(64)` holding `"u_moodyoak"` into `INTEGER REFERENCES users(id)` needs an
`ALTER … TYPE … USING`, and there is no `USING` expression that turns a
browser-invented label into a user id. That is why the change ships with a
one-time destructive reset instead:

```
ALLOW_DB_RESET=1 python scripts/reset_db.py --yes
```

It requires both the flag and the environment variable, prints what it is about
to destroy, and **never touches the dog corpus** — re-ingesting 226 MB is not
something to do by accident. It is deliberately not wired into `deploy.yml`: a
destructive step must not run on every push. Run it once, by hand, between
`docker compose pull` and `up -d`. (`docker compose down -v` is the wrong tool —
it would take `dogdata` with it.)

The schema now moves regularly, so **Alembic is the next step**, with the
post-reset schema as its baseline revision.

---

## 5. Ingest

### 5.1 Running it

`backend/scripts/ingest_dogs.py` takes a path to the extracted dataset. Point it
at the whole AFHQ archive and it finds the dogs itself — cats and wild animals
are skipped by directory name, and `train`/`val` become the `source_split` — or
point it at a flat folder of dog photos and it takes everything.

```bash
# locally, against the extracted Kaggle download
python scripts/ingest_dogs.py --source ~/Downloads/afhq

# on the VM, once
scp -r ~/Downloads/afhq azureuser@<vm-ip>:~/afhq
docker compose run --rm -v ~/afhq:/seed:ro model \
    python scripts/ingest_dogs.py --source /seed
```

The dataset is **not** committed to git: 226 MB of binaries would slow every CI
checkout and every Lovable sync, and would need Git LFS. Tests generate
synthetic images instead (§8), so CI never needs the real corpus.

### 5.2 What it guarantees

- **Idempotent.** Keyed on the **slug** (the filename, which is also what nginx
  serves). Re-running skips anything already present *with its derivatives
  intact* — a row whose pixels were lost with a volume is redone rather than
  skipped. Interrupt it and run it again.
- **Duplicate-tolerant.** AFHQ ships some byte-identical photos under different
  filenames, so `checksum` is indexed but not unique — one duplicate must not
  abort a 5,239-image run. The run reports how many it found, because a dog
  present twice is twice as likely to be retrieved, which quietly biases
  matching. Whether to drop them is a decision for the embedding phase.
- **Safe decode.** Pillow with `MAX_IMAGE_PIXELS` capped, `verify()` before
  decode, EXIF dropped, everything converted to RGB. A decompression bomb or a
  renamed non-image is rejected with a reason, not a traceback.
- **Parallel.** Decode and resize run in a `ProcessPoolExecutor` — it is CPU
  work outside the GIL, and it takes the wall clock from ~7 minutes to ~90
  seconds on 4 cores.

### 5.3 The one coupling to watch

The backend identifies a dog by its **index** into `src/lib/dogImages.json`
(`game/content.py` passes `dog_index`; `dogSrc.ts` resolves it to a filename).
That manifest is baked into the `site` image at build time, while ingest runs on
the VM at runtime — so the two can drift.

Rather than make the frontend fetch the manifest on every load, ingest
**verifies** its ordering against the committed file and fails loudly on a
mismatch. `--write-manifest` regenerates it for when the corpus legitimately
changes, and `/api/dogs/manifest` exposes the DB's version for tooling. Moving
the wire format from indices to slugs would remove the coupling entirely; that
is a follow-up, because it touches the game engine and its tests.

---

## 6. Limits & safety

| | limit | enforced |
|---|---|---|
| Upload file size | 10 MB | `uploads/router.py`, pre-existing |
| Uploads per request | 20 | new |
| Accepted types | PNG, JPEG — **by magic bytes**, not the declared header | pre-existing |
| Decode size | 50 MP | `storage/imaging.py` |
| DM attachment: image | 10 MB, JPEG/PNG/WebP | `dm/attachments.py` |
| DM attachment: video | 25 MB, MP4/WebM | `dm/attachments.py` |
| Request body (nginx) | 30 MB | `nginx.conf` — see below |

⚠️ **nginx used to cap request bodies at its 1 MB default**, so every photo over
1 MB was rejected with a 413 in production *before* FastAPI's own 10 MB limit
was consulted. `client_max_body_size 30m` in the `location /api/` block is what
makes both the upload cap and video attachments real.

Every uploaded image is **re-encoded**, never stored as received. That is what
strips EXIF (including GPS), applies the orientation tag so photos aren't
sideways, and destroys any payload smuggled in a metadata segment. The bytes on
disk are bytes Pillow wrote. The same is true of image attachments in DMs.

**Video is the exception, and it is worth being honest about.** There is no
decoder — shipping ffmpeg to transcode or even to probe would add 100 MB+ to an
image that already carries a 350 MB ONNX encoder, and minutes of CPU per clip on
a 1 GB VM. So a video is stored byte-for-byte, and the defences are arranged
around that: the container is identified from its own magic bytes; the extension
on disk and the `Content-Type` in the response both come from our allowlist;
responses carry `X-Content-Type-Options: nosniff`; the size cap is enforced
*while streaming*, not after buffering; and nginx never serves the directory, so
every read goes through the participant check. The residual risk is a
well-formed file no browser can play — a disappointment, not a hazard.

One consequence of no transcoding: **there is no server-generated poster frame.**
The UI appends `#t=0.1` to the video URL so the browser paints the first frame
itself, and the inbox preview shows "🎬 Video" rather than loading 25 MB to draw
a 40 px thumbnail.

**Retention:** an upload's files live exactly as long as its job row; deleting a
job deletes its derivatives. Attachments follow the same rule against their
message row. Deleting an account erases every photo and attachment it owns —
including attachments it *sent* to other people, because a picture of the
sender's face is their personal data wherever it now sits.

**Access.** A user photo is returned if the match is **shared to the gallery**
(no authentication — sharing is an explicit, reversible publication by the
owner), **or** the requester owns it, **or** it backs a forum post and the
requester is logged in. Everything else is a 404. Since the check re-runs
against the row on every request and responses are `no-store`, unsharing takes
effect immediately rather than whenever a cache expires.

Because an `<img>` or `<video>` element cannot send an `Authorization` header, a
private read carries a short-lived, `scope: "media"` token in the query string
instead. The two token kinds refuse each other, so one leaking into an access
log is not a session handover.

---

## 7. The matching model

**The constraint that shapes everything: there are no human/dog training
pairs.** Nothing supervised is possible — no fine-tuning, no learned
projection, no ground truth to fit. Matching is zero-shot on top of CLIP.

### 7.1 Why the obvious approach fails

Embed both with CLIP, take the cosine, return the nearest dog — and you get an
effectively random dog, and often the *same* dog for everybody. CLIP embeddings
are dominated by *what kind of thing* is pictured: every dog lands in one tight
cluster, every human in another, and the gap between the clusters swamps the
variation within them. Two corrections fix it, and both are load-bearing.

**Species-mean centring.** Subtract the mean dog vector from every dog and the
mean human vector from every human before comparing. That throws away "is a
dog" versus "is a person" — a constant offset carrying no information about
resemblance — and leaves how each face differs from its own kind, which is the
axis resemblance actually lives on.

**A shared attribute space.** Score both species against the same sixteen text
prompts (`app/ml/attributes.py`) and compare *those* scores. Species-neutral by
construction, and the only part of the pipeline that can say **why** — the
traits where both the person and the dog are unusually high.

The two are blended evenly (`MATCH_EMBEDDING_WEIGHT`, default 0.5): the
embedding side carries more information, the attribute side generalises better
across the species gap and is much harder to fool.

> **The attribute prompts must be mean-centred, and this is not cosmetic.**
> CLIP's text embeddings sit in a narrow cone. Straight out of the model, every
> pair of our sixteen attributes scored ~+0.85 against every other — "fluffy"
> and "sleek", opposites, came out at +0.862 — so each score was mostly
> measuring the cone rather than the trait. Subtracting the mean attribute
> takes fluffy/sleek to **-0.145**, keeps fluffy/shaggy positive at +0.384,
> puts golden/dark at +0.005, and drops mean pairwise similarity from +0.851 to
> **-0.065**: a near-orthogonal vocabulary instead of sixteen near-copies.
> `scripts/export_encoder.py` does it; two tests guard it, because dropping it
> degrades matching badly and *silently*.

### 7.2 Face cropping

AFHQ dogs are tight, centred head crops; an upload is whatever was on someone's
phone. Without cropping, most of a human vector describes the sofa. `app/ml/faces.py`
detects with YuNet (232KB, vendored) and crops to a square with 45% margin to
match AFHQ's framing. **No face means no match** — which is also the
guidelines' "robust to a picture meant to make the model not output a dog": a
photo of a sandwich gets a clear rejection, not a confident dog.

### 7.3 Packaging: ONNX at runtime, PyTorch never

PyTorch is ~2GB and CI pushes and the VM pulls the image on every deploy, so it
does not ship. `scripts/export_encoder.py` exports CLIP's image tower to ONNX
once; the container runs it under onnxruntime (~15MB). The backend `Dockerfile`
does this in a **discarded first stage**: torch is installed there, the export
runs, and only the resulting graph is copied forward. The export layer is cached
in GitHub Actions, so it is rebuilt only when `requirements-ml.txt` changes.

Only the *image* tower is exported — the text tower's whole job is those sixteen
fixed prompts, so it runs once offline and the vectors are committed (32KB).

### 7.4 The three offline passes

| Script | Needs | Run when |
|---|---|---|
| `export_encoder.py` | `requirements-ml.txt` (torch) | once per model change; the Docker build does it for production |
| `embed_dogs.py` | runtime deps only | after `ingest_dogs.py`, and after any vocabulary change |
| `calibrate_humans.py` | runtime deps + a folder of face photos | once per model change |

`embed_dogs.py` deliberately needs no PyTorch — it uses the exported graph, so
dogs and uploads go through byte-identical preprocessing, and it can run on the
VM exactly like the ingest.

`calibrate_humans.py` computes the human mean and spread from a reference face
set (LFW is convenient and freely available). **The images are read and thrown
away** — only aggregate statistics are stored, so there is no dataset to
redistribute and no face is retained. The dog statistics are *not* stored: they
are derived from the corpus at load time, so they cannot drift out of step with
the vectors they describe.

### 7.5 The score

The number shown to a user is **distinctiveness**, not probability: where the
winning similarity sits in the corpus's own distribution, squashed to 0-1. A
high number means "this dog fits much better than the other 5,238", not "97%
likely correct". The raw cosine would be useless on its own — after centring it
lands in a narrow band where 0.19 is a great match.

### 7.6 What has been measured

Run on the real corpus (5,239 AFHQ dogs, all embedded) against 300 real faces
from LFW, via `scripts/evaluate_matching.py`:

| check | result | why it matters |
|---|---|---|
| Distinct dogs | **280 / 300** (diversity 0.93) | The characteristic failure of naive CLIP matching is *collapse* — the species gap dominates and one dog wins for everybody. It isn't happening. |
| Most common dog | **1.0%** of faces | Collapse would put this near 100%. |
| Separation | **3.61σ** above the corpus mean | The winner is not a coin flip among 5,239. |
| Stability | same photo → same dog | A refresh can't contradict the demo. |
| Attribute grounding | mean **+0.707** rank correlation | Each attribute axis agrees with a *held-out wording* of the same trait, so the traits shown to users mean something. Range +0.44 (round face) to +0.85 (greying). |

Also verified: the ONNX export agrees with PyTorch to **2e-6** (the export script
refuses to ship past 1e-3), and the full runtime path — our preprocessing plus
the exported graph — correctly zero-shot-captions a real photograph (+0.300 for
the true caption against +0.181/+0.175/+0.126), which a preprocessing bug would
break. Face detection found a face in **1500/1500** LFW images.

> **On the grounding metric.** The held-out probes are mean-centred exactly as
> the real attribute vectors are. Comparing a centred axis against an uncentred
> reference understates agreement badly — it reported mean +0.52 and put "sleek"
> at +0.08, which reads as a broken attribute when it is really a broken
> yardstick (the same axis scores +0.63 measured correctly). Independence comes
> from the *wording* being held out, not from the geometry differing. An earlier
> version of the script compared each axis against its own prompt vector, which
> is worse still: those are the same quantity up to a per-row scale, so it
> returned +0.997 for everything and proved only that a number equals itself.

**Still a matter of judgement:** whether the dogs actually *look* like the
people. Every metric above says the model discriminates, is stable, and its
attributes track real traits — none of them can say the result is funny or
flattering, which is what the project is ultimately for. That needs a human
looking at output.

## 8. Testing

No binaries in the repo: `backend/tests/conftest.py` generates deterministic
synthetic images at test time. The suite covers the imaging primitives (EXIF
stripped, RGBA flattened, bombs rejected, corrupt bytes rejected), the ingest
(rows created, derivatives written, re-run is a no-op, manifest indices dense
and sorted), the dog metadata endpoint, and the upload path end to end
including the ownership check on image reads.

CI needs no dataset, no volume and no Postgres — it runs against SQLite and a
temp directory, exactly as the game tests already do.
