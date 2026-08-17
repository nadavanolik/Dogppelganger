import type { DogRef } from "@/lib/uploadApi";

const BOX = { sm: "h-16 w-16", md: "h-24 w-24", lg: "h-40 w-40" } as const;

/**
 * A completed match: the person, an arrow, the dog they drew.
 *
 * This replaced the breed name that used to sit next to the human photo. AFHQ
 * has no breed labels, so the old "Golden Retriever" caption was invented by a
 * hash and would cheerfully sit above a photo of a pug. Showing the retrieved
 * dog itself is both honest and the thing the user actually came for.
 */
export function MatchPair({
  humanSrc,
  dog,
  score,
  sharedTraits = [],
  size = "md",
}: {
  humanSrc: string;
  dog: DogRef | null;
  score?: number | null;
  sharedTraits?: string[];
  size?: "sm" | "md" | "lg";
}) {
  const box = BOX[size];
  const frame = `${box} object-cover rounded-xl border-2 border-[var(--ink)] shrink-0`;

  return (
    <div className="flex items-center gap-3">
      <img src={humanSrc} alt="the uploaded photo" className={frame} />
      <span className="text-xl shrink-0" aria-hidden="true">
        →
      </span>
      {dog ? (
        <img
          // The 512px copy only where the photo is the point of the page;
          // everywhere else 256 is plenty and a third of the bytes.
          src={size === "lg" ? dog.fullUrl : dog.imageUrl}
          alt="the matched dog"
          className={frame}
        />
      ) : (
        <div className={`${frame} grid place-items-center bg-muted text-2xl`} aria-hidden="true">
          🐾
        </div>
      )}
      <div className="min-w-0">
        {score != null && (
          <div className="font-display font-bold leading-tight">
            {Math.round(score * 100)}% match
          </div>
        )}
        {sharedTraits.length > 0 && (
          <div className="text-xs text-muted-foreground italic">
            you both read as {sharedTraits.join(" · ")}
          </div>
        )}
      </div>
    </div>
  );
}
