import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { DogCard } from "@/components/DogCard";
import { BREEDS } from "@/lib/mock";
import { useStore } from "@/lib/store";

export const Route = createFileRoute("/gallery")({ component: Gallery });

function Gallery() {
  const { state } = useStore();
  const [breed, setBreed] = useState<string>("all");
  const all = state.matches.filter((m) => m.shared && m.status === "done");
  const filtered = useMemo(() => (breed === "all" ? all : all.filter((m) => m.breedName === breed)), [all, breed]);

  return (
    <AppShell>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-5xl font-black">Public gallery</h1>
          <p className="text-muted-foreground mt-1">Every match shared by the pack. Feeds the multiplayer game.</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <FilterChip active={breed === "all"} onClick={() => setBreed("all")}>All ({all.length})</FilterChip>
          {BREEDS.map((b) => {
            const count = all.filter((m) => m.breedName === b.name).length;
            if (count === 0) return null;
            return (
              <FilterChip key={b.name} active={breed === b.name} onClick={() => setBreed(b.name)}>
                {b.emoji} {b.name}
              </FilterChip>
            );
          })}
        </div>
      </div>
      {filtered.length === 0 ? (
        <div className="card-pop p-10 text-center mt-8">
          <div className="text-6xl">🦴</div>
          <div className="font-display text-2xl font-bold mt-2">No shared matches yet</div>
          <div className="text-muted-foreground">Upload one and hit share.</div>
        </div>
      ) : (
        <div className="mt-6 grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
          {filtered.map((m) => <DogCard key={m.id} match={m} />)}
        </div>
      )}
    </AppShell>
  );
}

function FilterChip({ active, ...p }: { active: boolean } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button {...p} className={`btn-pop btn-pop-hover px-3 py-1.5 text-sm ${active ? "bg-primary text-primary-foreground" : "bg-card"}`} />;
}
