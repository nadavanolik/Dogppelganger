import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/AppShell";
import { isPhoto, isKnownDogImage } from "@/lib/mock";
import { useStore } from "@/lib/store";
import type { DogMatch } from "@/lib/store";

export const Route = createFileRoute("/gallery")({ component: Gallery });

function Gallery() {
  const { state } = useStore();
  // Only show shared matches whose dog picture is a real file in public/dogs — drop any card
  // pointing at a deleted or renamed image.
  const shared = state.matches.filter((m) => m.shared && m.status === "done" && isKnownDogImage(m.breedImage));

  return (
    <AppShell>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-5xl font-black">Public gallery</h1>
          <p className="text-muted-foreground mt-1">Every match shared by the pack. Feeds the multiplayer game.</p>
        </div>
        <div className="text-sm font-bold text-muted-foreground">{shared.length} shared</div>
      </div>
      {shared.length === 0 ? (
        <div className="card-pop p-10 text-center mt-8">
          <div className="text-6xl">🦴</div>
          <div className="font-display text-2xl font-bold mt-2">No shared matches yet</div>
          <div className="text-muted-foreground">Upload one and hit share.</div>
        </div>
      ) : (
        <div className="mt-6 grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
          {shared.map((m) => <MatchCard key={m.id} match={m} />)}
        </div>
      )}
    </AppShell>
  );
}

// Gallery card: human photo and dog photo side by side (same match, same number). No breed name.
function MatchCard({ match }: { match: DogMatch }) {
  return (
    <div className="card-pop-sm overflow-hidden">
      <div className="grid grid-cols-2">
        <Face src={match.humanImg} fallback="🧑" />
        <Face src={match.breedImage ?? match.breedEmoji} fallback={match.breedEmoji} bg={match.breedBg} />
      </div>
      <div className="p-3 text-xs text-muted-foreground">@{match.username}</div>
    </div>
  );
}

function Face({ src, fallback, bg }: { src: string; fallback: string; bg?: string }) {
  return (
    <div className={`h-40 flex items-center justify-center overflow-hidden ${bg ? `bg-gradient-to-br ${bg}` : "bg-muted"}`}>
      {isPhoto(src) ? (
        <img src={src} alt="" className="w-full h-full object-cover" />
      ) : (
        <span className="text-6xl">{src || fallback}</span>
      )}
    </div>
  );
}
