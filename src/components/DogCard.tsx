import { dogSrc } from "@/lib/dogSrc";
import type { SharedTrait } from "@/lib/uploadApi";

/**
 * One human-to-dog pair in the gallery.
 *
 * Takes plain props rather than the old mock `DogMatch` object, so the same
 * card serves the public gallery and the landing page from real API data.
 * `humanUrl` is the shared match's photo, served by the API — for a shared
 * match it needs no token, because sharing is what makes it public.
 */
export function DogCard({
  dogIndex,
  humanUrl,
  username,
  sharedTraits = [],
  size = "md",
}: {
  dogIndex: number | null;
  humanUrl?: string | null;
  username: string;
  sharedTraits?: SharedTrait[];
  size?: "sm" | "md" | "lg";
}) {
  const dim = size === "sm" ? "h-32" : size === "lg" ? "h-72" : "h-52";

  return (
    <div className="card-pop-sm overflow-hidden">
      <div className={`${dim} bg-muted flex items-center justify-center relative overflow-hidden`}>
        {dogIndex != null ? (
          <img
            src={dogSrc(dogIndex, size === "lg" ? "512" : "256")}
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
          {humanUrl ? (
            <img
              src={humanUrl}
              alt="the person"
              className="h-8 w-8 rounded-lg border-2 border-[var(--ink)] object-cover"
            />
          ) : (
            <span className="text-2xl">🧑</span>
          )}
          <span className="text-xl" aria-hidden="true">
            →
          </span>
          <span className="text-2xl" aria-hidden="true">
            🐶
          </span>
        </div>
        {sharedTraits.length > 0 && (
          <div className="mt-1 text-xs text-muted-foreground italic">
            {sharedTraits.map((t) => t.label).join(" · ")}
          </div>
        )}
        <div className="mt-1 text-xs text-muted-foreground">@{username}</div>
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
