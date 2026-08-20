import { dogSrc } from "@/lib/dogSrc";
import type { DogMatch } from "@/lib/store";

export function DogCard({ match, size = "md" }: { match: DogMatch; size?: "sm" | "md" | "lg" }) {
  const dim = size === "sm" ? "h-32" : size === "lg" ? "h-72" : "h-52";

  return (
    <div className="card-pop-sm overflow-hidden">
      <div className={`${dim} bg-muted flex items-center justify-center relative overflow-hidden`}>
        {match.dogIndex != null ? (
          <img
            src={dogSrc(match.dogIndex, size === "lg" ? "512" : "256")}
            alt="the matched dog"
            className="w-full h-full object-cover"
          />
        ) : (
          <span className="text-6xl" aria-hidden="true">
            🐾
          </span>
        )}
      </div>
      <div className="p-3">
        <div className="flex items-center gap-2">
          <span className="text-2xl">{match.humanImg.length <= 4 ? match.humanImg : "🧑"}</span>
          <span className="text-xl" aria-hidden="true">
            →
          </span>
          <span className="text-2xl" aria-hidden="true">
            🐶
          </span>
        </div>
        {match.sharedTraits && match.sharedTraits.length > 0 && (
          <div className="mt-1 text-xs text-muted-foreground italic">
            {match.sharedTraits.map((t) => t.label).join(" · ")}
          </div>
        )}
        <div className="mt-1 text-xs text-muted-foreground">@{match.username}</div>
      </div>
    </div>
  );
}

export function HumanAvatar({ src, size = 64 }: { src: string; size?: number }) {
  if (src.startsWith("data:") || src.startsWith("http")) {
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
