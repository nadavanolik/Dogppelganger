import type { DogRef, SharedTrait } from "@/lib/uploadApi";

/**
 * One human-to-dog pair in the gallery.
 *
 * Both photos show at equal size, side by side — a shared match is about the
 * pair, and a tiny avatar next to a big dog buried the half of the story that
 * makes the resemblance judgeable at a glance.
 *
 * Takes plain props rather than the old mock `DogMatch` object, so the same
 * card serves the public gallery and the landing page from real API data.
 * `humanUrl` is the shared match's photo, served by the API — for a shared
 * match it needs no token, because sharing is what makes it public.
 */
export function DogCard({
  dog,
  humanUrl,
  username,
  sharedTraits = [],
  size = "md",
}: {
  dog: DogRef | null;
  humanUrl?: string | null;
  username: string;
  sharedTraits?: SharedTrait[];
  size?: "sm" | "md" | "lg";
}) {
  const dim = size === "sm" ? "h-32" : size === "lg" ? "h-72" : "h-52";

  return (
    <div className="card-pop-sm overflow-hidden">
      <div className={`${dim} flex relative`}>
        <div className="flex-1 bg-muted overflow-hidden">
          {humanUrl ? (
            <img src={humanUrl} alt="the person" className="w-full h-full object-cover" />
          ) : (
            <div className="w-full h-full grid place-items-center text-4xl" aria-hidden="true">
              🧑
            </div>
          )}
        </div>
        <div className="flex-1 bg-muted overflow-hidden border-l-2 border-[var(--ink)]">
          {dog ? (
            <img
              src={size === "lg" ? dog.fullUrl : dog.imageUrl}
              alt="the matched dog"
              className="w-full h-full object-cover"
            />
          ) : (
            <div className="w-full h-full grid place-items-center text-4xl" aria-hidden="true">
              🐾
            </div>
          )}
        </div>
        <span
          className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 h-7 w-7 rounded-full border-2 border-[var(--ink)] bg-card grid place-items-center text-sm shadow-pop-sm"
          aria-hidden="true"
        >
          →
        </span>
      </div>
      <div className="p-3">
        {sharedTraits.length > 0 && (
          <div className="text-xs text-muted-foreground italic">
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
