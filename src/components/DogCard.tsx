import type { DogMatch } from "@/lib/store";
import { isPhoto } from "@/lib/mock";

export function DogCard({ match, size = "md" }: { match: DogMatch; size?: "sm" | "md" | "lg" }) {
  const dim = size === "sm" ? "h-32" : size === "lg" ? "h-72" : "h-52";
  const emoji = size === "sm" ? "text-5xl" : size === "lg" ? "text-9xl" : "text-7xl";
  return (
    <div className={`card-pop-sm overflow-hidden`}>
      <div className={`${dim} bg-gradient-to-br ${match.breedBg} flex items-center justify-center relative overflow-hidden`}>
        {match.breedImage ? (
          <img src={match.breedImage} alt={match.breedName} className="w-full h-full object-cover" />
        ) : (
          <span className={emoji}>{match.breedEmoji}</span>
        )}
      </div>
      <div className="p-3">
        <div className="flex items-center gap-2">
          {isPhoto(match.humanImg) ? (
            <img src={match.humanImg} alt="" className="h-7 w-7 rounded-full border border-[var(--ink)] object-cover" />
          ) : (
            <span className="text-2xl">{match.humanImg}</span>
          )}
          <span className="text-xl">→</span>
          <span className="text-2xl">{match.breedEmoji}</span>
        </div>
        <div className="mt-1 font-display text-lg font-bold leading-tight">{match.breedName}</div>
        <div className="text-xs text-muted-foreground italic">{match.trait}</div>
        <div className="mt-1 text-xs text-muted-foreground">@{match.username}</div>
      </div>
    </div>
  );
}

export function HumanAvatar({ src, size = 64 }: { src: string; size?: number }) {
  if (isPhoto(src)) {
    return (
      <img
        src={src}
        alt="uploaded"
        className="rounded-2xl border-2 object-cover"
        style={{ borderColor: "var(--ink)", width: size, height: size }}
      />
    );
  }
  return (
    <div
      className="rounded-2xl border-2 flex items-center justify-center bg-sunshine"
      style={{ borderColor: "var(--ink)", width: size, height: size, fontSize: size * 0.55 }}
    >
      {src || "🧑"}
    </div>
  );
}
