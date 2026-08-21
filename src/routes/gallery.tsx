import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { DogCard } from "@/components/DogCard";
import { galleryApi, type GalleryItem } from "@/lib/galleryApi";

export default Gallery;

const PAGE = 24;

/**
 * The public gallery: human-to-dog matches their owners chose to publish.
 *
 * Not "every post with a picture" — a forum post can carry a photo without
 * being a match, and sharing a match is its own act. Nothing appears here
 * unless someone pressed Share, and unsharing removes it on the next request.
 *
 * Readable logged-out, because the landing page shows a strip of it to visitors
 * who don't have an account yet.
 */
function Gallery() {
  const [items, setItems] = useState<GalleryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    galleryApi
      .list(PAGE, 0)
      .then((res) => {
        setItems(res.items);
        setTotal(res.total);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Couldn't load the gallery."))
      .finally(() => setLoading(false));
  }, []);

  async function loadMore() {
    const res = await galleryApi.list(PAGE, items.length);
    setItems((prev) => [...prev, ...res.items]);
    setTotal(res.total);
  }

  return (
    <AppShell>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-5xl font-black">Public gallery</h1>
          <p className="text-muted-foreground mt-1">
            Every match shared by the pack. Feeds the multiplayer game.
          </p>
        </div>
        <span className="btn-pop bg-card px-4 py-2 text-sm font-bold">{total} shared</span>
      </div>

      {error && <div className="mt-6 text-destructive text-sm">{error}</div>}

      {!loading && items.length === 0 ? (
        <div className="card-pop p-10 text-center mt-8">
          <div className="text-6xl">🦴</div>
          <div className="font-display text-2xl font-bold mt-2">No shared matches yet</div>
          <div className="text-muted-foreground">Upload one and hit share.</div>
        </div>
      ) : (
        <>
          <div className="mt-6 grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
            {items.map((item) => (
              <DogCard
                key={item.jobId}
                dogIndex={item.dogIndex}
                humanUrl={item.thumbUrl}
                username={item.owner.username}
                sharedTraits={item.sharedTraits}
              />
            ))}
          </div>
          {items.length < total && (
            <button
              onClick={loadMore}
              className="btn-pop btn-pop-hover bg-card px-5 py-2 mt-6 mx-auto block"
            >
              Load more
            </button>
          )}
        </>
      )}
    </AppShell>
  );
}
