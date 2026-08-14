import { dogSrc } from "@/lib/dogSrc";

export type OptionState = "idle" | "picked" | "correct" | "wrong" | "dimmed";

const RING: Record<OptionState, string> = {
  idle: "",
  picked: "ring-4 ring-[var(--sky)]",
  correct: "ring-4 ring-[var(--mint)]",
  wrong: "ring-4 ring-[var(--destructive)]",
  dimmed: "opacity-45",
};

/** One dog photo the player can pick. */
export function DogOption({
  dogIndex,
  label,
  state = "idle",
  disabled,
  onClick,
}: {
  dogIndex: number;
  label: string;
  state?: OptionState;
  disabled?: boolean;
  onClick?: () => void;
}) {
  const badge =
    state === "correct" ? "✅" : state === "wrong" ? "❌" : state === "picked" ? "👉" : label;

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      aria-label={`Dog ${label}`}
      className={`card-pop-sm relative overflow-hidden group ${RING[state]} ${
        disabled ? "cursor-default" : "btn-pop-hover cursor-pointer"
      }`}
    >
      <img
        src={dogSrc(dogIndex)}
        alt=""
        loading="eager"
        className="w-full aspect-square object-cover"
      />
      <span
        className={`absolute top-2 left-2 h-9 min-w-9 px-2 grid place-items-center rounded-full border-2 border-[var(--ink)] font-display text-lg font-black ${
          state === "correct"
            ? "bg-mint"
            : state === "wrong"
              ? "bg-destructive text-destructive-foreground"
              : "bg-card"
        }`}
      >
        {badge}
      </span>
    </button>
  );
}

/** The human half of a question. */
export function QuestionPrompt({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-center">
      <div className="text-sm font-bold text-muted-foreground uppercase tracking-wide">
        Which dog is this human?
      </div>
      <div className="mt-3 flex justify-center">{children}</div>
    </div>
  );
}
