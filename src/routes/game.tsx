import { useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { BREEDS } from "@/lib/mock";
import { useStore, type DogMatch } from "@/lib/store";

export default Game;

function pickChoices(target: DogMatch): string[] {
  const others = BREEDS.filter((b) => b.name !== target.breedName)
    .sort(() => Math.random() - 0.5)
    .slice(0, 3)
    .map((b) => b.name);
  return [...others, target.breedName].sort(() => Math.random() - 0.5);
}

function Game() {
  const { state } = useStore();
  const pool = useMemo(
    () => state.matches.filter((m) => m.shared && m.status === "done"),
    [state.matches],
  );
  const [i, setI] = useState(0);
  const [score, setScore] = useState(0);
  const [picked, setPicked] = useState<string | null>(null);
  const target = pool[i % Math.max(pool.length, 1)];
  const choices = useMemo(() => (target ? pickChoices(target) : []), [target]);

  if (!target) {
    return (
      <AppShell>
        <div className="card-pop max-w-xl mx-auto p-8 text-center">
          <div className="text-6xl">🎮</div>
          <h1 className="font-display text-3xl font-black mt-2">No shared matches yet</h1>
          <p className="text-muted-foreground">
            Once people share to the gallery, the game fills up automatically.
          </p>
        </div>
      </AppShell>
    );
  }

  const correct = picked === target.breedName;

  return (
    <AppShell>
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center justify-between mb-4">
          <h1 className="font-display text-4xl font-black">Guess the breed</h1>
          <div className="btn-pop bg-sunshine px-3 py-1">Score: {score}</div>
        </div>
        <div className="card-pop p-8">
          <div className="text-sm font-bold text-muted-foreground text-center">
            This human is a…?
          </div>
          <div className="mt-4 flex justify-center">
            {target.humanImg.startsWith("data:") ? (
              <img
                src={target.humanImg}
                alt=""
                className="h-56 w-56 object-cover rounded-2xl border-2 border-[var(--ink)]"
              />
            ) : (
              <div className="h-56 w-56 rounded-2xl border-2 border-[var(--ink)] bg-sky flex items-center justify-center text-8xl">
                {target.humanImg}
              </div>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3 mt-6">
            {choices.map((c) => {
              const isRight = c === target.breedName;
              const state =
                picked == null
                  ? ""
                  : c === picked
                    ? isRight
                      ? "bg-mint"
                      : "bg-destructive text-destructive-foreground"
                    : isRight
                      ? "bg-mint"
                      : "opacity-60";
              return (
                <button
                  key={c}
                  disabled={picked !== null}
                  onClick={() => {
                    setPicked(c);
                    if (c === target.breedName) setScore((s) => s + 1);
                  }}
                  className={`btn-pop btn-pop-hover px-4 py-3 text-lg ${state || "bg-card"}`}
                >
                  {c}
                </button>
              );
            })}
          </div>
          {picked && (
            <div className="mt-6 text-center">
              <div className="text-2xl">
                {correct ? "🎉 Correct!" : "❌ Nope."} The answer was {target.breedEmoji}{" "}
                {target.breedName}.
              </div>
              <button
                onClick={() => {
                  setPicked(null);
                  setI(i + 1);
                }}
                className="btn-pop btn-pop-hover bg-primary text-primary-foreground mt-3 px-5 py-2"
              >
                Next →
              </button>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
