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

1. **Store the dog corpus** so the site can actually show a dog. ← *this phase*
2. **Store user photos** safely, and the human↔dog pair each match produces. ← *this phase*
3. **Replace the hash stub** with real retrieval over the corpus. ← *next phase*

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
scored alike on ("fluffy", "sleepy eyes", "long face"). It is a column now,
populated for real in the next phase (§7).

---

## 3. On-disk layout

```
dogdata volume
├── 512/flickr_dog_000002.jpg     archival · JPEG q90 · EXIF stripped
├── 256/flickr_dog_000002.webp    display  · WebP q82   ~15 KB
└── 128/flickr_dog_000002.webp    thumb / game tile · WebP q80  ~5 KB

appdata volume  (/app/data)
├── game/                         existing leaderboard snapshots — untouched
└── uploads/0000/                 sharded by job_id // 1000
    ├── 17-orig.jpg               re-encoded original, ≤ 1024 px
    ├── 17-display.webp           512 px
    └── 17-thumb.webp             256 px
```

Uploads are sharded because a single directory holding tens of thousands of
entries degrades on ext4. `job_id // 1000` keeps ~3,000 files per directory and,
unlike hashing the owner id, puts nothing user-identifying in a path.

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
| `embedding` | bytes | `float32` vector, `np.ndarray.tobytes()`; NULL until phase 2 |
| `embedding_dim`, `embedding_model` | int, str | so a model swap invalidates cleanly |
| `attributes`, `attribute_set` | bytes, str | the attribute vector behind `shared_traits` |

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

---

## 5. Ingest

### 5.1 Running it

`backend/scripts/ingest_dogs.py` takes a path to the extracted AFHQ dog folder.
It accepts both the dataset's own `train/dog` + `val/dog` layout and a flat
directory of images.

```bash
# locally, against a checkout of the Kaggle dataset
python scripts/ingest_dogs.py --source ~/afhq/dog

# on the VM, once
scp -r ~/afhq/dog azureuser@<vm-ip>:~/afhq-dog
docker compose run --rm -v ~/afhq-dog:/seed:ro model \
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
| Forum image / video | 5 MB / 25 MB | phase 3, documented not built |

Every uploaded image is **re-encoded**, never stored as received. That is what
strips EXIF (including GPS), applies the orientation tag so photos aren't
sideways, and destroys any payload smuggled in a metadata segment. The bytes on
disk are bytes Pillow wrote.

**Retention:** an upload's files live exactly as long as its job row; deleting a
job deletes its derivatives. Default unless someone says otherwise.

---

## 7. The model seam (next phase)

`backend/app/model.py` exposes exactly one function:

```python
def match_dog(db: Session, image_path: Path) -> DogMatchResult
```

Today it is a deterministic stub that hashes the file's checksum and picks a
real dog from `dog_assets` — the whole stack works end to end, it just isn't
*similarity* yet. **Only this function changes next phase.** The queue, the
routers, the schema and the frontend are already speaking in dog references.

The plan for the real one, given that we have **no human↔dog training pairs**:

1. **CLIP image embeddings** for both sides.
2. **Species-mean centring** — subtract the mean human embedding from human
   vectors and the mean dog embedding from dog vectors before comparing. Raw
   CLIP cosine between a person and a dog is dominated by "human vs dog", which
   makes the nearest dog nearly random; centring removes that shared direction.
3. **A text-attribute bridge** — score both species against the same CLIP text
   prompts ("fluffy", "grumpy", "long face", "sleepy eyes") and match in that
   shared, species-invariant space. This is also what makes `shared_traits`
   explainable rather than a bare percentage.

Blocked on knowing the VM's specs — CLIP ViT-B/32 wants ~1 GB of RAM, which an
Azure B1s does not have.

---

## 8. Testing

No binaries in the repo: `backend/tests/conftest.py` generates deterministic
synthetic images at test time. The suite covers the imaging primitives (EXIF
stripped, RGBA flattened, bombs rejected, corrupt bytes rejected), the ingest
(rows created, derivatives written, re-run is a no-op, manifest indices dense
and sorted), the dog metadata endpoint, and the upload path end to end
including the ownership check on image reads.

CI needs no dataset, no volume and no Postgres — it runs against SQLite and a
temp directory, exactly as the game tests already do.
