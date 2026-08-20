import type { DogRef, SharedTrait } from "@/lib/uploadApi";

const BOX = { sm: "h-16 w-16", md: "h-24 w-24", lg: "h-40 w-40" } as const;

/**
 * A completed match: the person, an arrow, the dog they drew, and the traits
 * the two of them share.
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
  sharedTraits?: SharedTrait[];
  size?: "sm" | "md" | "lg";
}) {
  const box = BOX[size];
  const frame = `${box} object-cover rounded-xl border-2 border-[var(--ink)] shrink-0`;

  return (
    <div className="min-w-0">
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
        {score != null && (
          <div className="font-display font-bold leading-tight">
            {Math.round(score * 100)}% match
          </div>
        )}
      </div>

      <SharedTraits traits={sharedTraits} />
    </div>
  );
}

/**
 * The traits behind a match, under the photos that earned them.
 *
 * The percentage is the *weaker* side's percentile on that trait, so it reads
 * as "neither of you is below here" — not a confidence that the match is
 * correct. Older matches carry no strength and show the label alone rather
 * than a number that was never measured.
 */
export function SharedTraits({ traits }: { traits: SharedTrait[] }) {
  if (traits.length === 0) return null;

  return (
    <div className="mt-3">
      <div className="text-xs font-bold text-muted-foreground">you both read as</div>
      <ul className="mt-1 flex flex-wrap gap-1.5">
        {traits.map((trait) => (
          <li
            key={trait.label}
            className="flex items-baseline gap-1.5 rounded-full border-2 border-[var(--ink)] bg-mint px-2.5 py-0.5 text-xs"
          >
            <span className="font-bold">{trait.label}</span>
            {trait.strength != null && (
              <span className="tabular-nums opacity-70">{Math.round(trait.strength * 100)}%</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
