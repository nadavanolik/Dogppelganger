const MAX_LIVES = 3;

/** Lives left in a Streak Survival run. */
export function LivesHearts({ lives }: { lives: number }) {
  return (
    <span className="text-2xl leading-none tracking-widest" aria-label={`${lives} lives left`}>
      {Array.from({ length: MAX_LIVES }, (_, i) => (i < lives ? "❤️" : "🖤")).join("")}
    </span>
  );
}

/** Current streak, which gets louder the longer it runs. */
export function StreakFlame({ streak }: { streak: number }) {
  if (streak < 2) {
    return <span className="text-sm text-muted-foreground">no streak yet</span>;
  }
  const heat = streak >= 10 ? "🔥🔥🔥" : streak >= 5 ? "🔥🔥" : "🔥";
  return (
    <span className="font-display text-lg font-black">
      {heat} {streak} in a row
    </span>
  );
}

/** A big number with a caption, for score / best / rank tiles. */
export function StatTile({
  label,
  value,
  tint = "bg-card",
}: {
  label: string;
  value: React.ReactNode;
  tint?: string;
}) {
  return (
    <div className={`card-pop-sm px-4 py-3 text-center ${tint}`}>
      <div className="font-display text-3xl font-black leading-none">{value}</div>
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground mt-1">{label}</div>
    </div>
  );
}
