import { AppShell } from "@/components/AppShell";
import { DogCard } from "@/components/DogCard";
import { useStore } from "@/lib/store";

export default Gallery;

function Gallery() {
  const { state } = useStore();
  // The breed filter that used to sit here filtered on `breedName`, a label
  // invented per match and unrelated to the dog in the photo — so the chips
  // sorted matches into categories that never meant anything. Nothing real
  // replaces it until the corpus carries labels or the gallery is server-side.
  const all = state.matches.filter((m) => m.shared && m.status === "done");

  return (
    <AppShell>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-5xl font-black">Public gallery</h1>
          <p className="text-muted-foreground mt-1">
            Every match shared by the pack. Feeds the multiplayer game.
          </p>
        </div>
        <span className="btn-pop bg-card px-4 py-2 text-sm font-bold">{all.length} shared</span>
      </div>
      {all.length === 0 ? (
        <div className="card-pop p-10 text-center mt-8">
          <div className="text-6xl">🦴</div>
          <div className="font-display text-2xl font-bold mt-2">No shared matches yet</div>
          <div className="text-muted-foreground">Upload one and hit share.</div>
        </div>
      ) : (
        <div className="mt-6 grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
          {all.map((m) => (
            <DogCard key={m.id} match={m} />
          ))}
        </div>
      )}
    </AppShell>
  );
}
