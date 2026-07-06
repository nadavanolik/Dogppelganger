import { createFileRoute, Link, useRouter } from "@tanstack/react-router";
import { AppShell } from "@/components/AppShell";
import { HumanAvatar } from "@/components/DogCard";
import { useStore } from "@/lib/store";

export const Route = createFileRoute("/result/$id")({ component: Result });

function Result() {
  const { id } = Route.useParams();
  const { state, shareMatch, discardMatch } = useStore();
  const router = useRouter();
  const m = state.matches.find((x) => x.id === id);

  if (!m) {
    return <AppShell><div className="card-pop p-8 text-center">Match not found.</div></AppShell>;
  }
  const done = m.status === "done";

  return (
    <AppShell>
      <div className="max-w-3xl mx-auto card-pop p-8">
        {!done ? (
          <div className="text-center py-8">
            <div className="text-7xl animate-bounce">🐕</div>
            <div className="mt-4 font-display text-3xl font-black">{m.status === "queued" ? "In the queue…" : "Dogifying…"}</div>
            <p className="text-muted-foreground mt-1">{m.urgent ? "🚨 Urgent priority — coming right up." : "We'll ping you when it's ready."}</p>
            <Link to="/" className="btn-pop btn-pop-hover bg-primary text-primary-foreground inline-block mt-6 px-5 py-2">See queue</Link>
          </div>
        ) : (
          <>
            <div className="text-center">
              <div className="text-sm font-bold text-muted-foreground uppercase tracking-wide">Your dogppleganger is…</div>
              <h1 className="font-display text-5xl md:text-6xl font-black mt-1">{m.breedName}</h1>
              <p className="italic text-muted-foreground mt-1">{m.trait}</p>
            </div>
            <div className="mt-8 flex items-center justify-center gap-6">
              <HumanAvatar src={m.humanImg} size={144} />
              <div className="text-5xl">→</div>
              <div className={`h-36 w-36 rounded-2xl border-2 border-[var(--ink)] bg-gradient-to-br ${m.breedBg} flex items-center justify-center text-8xl relative overflow-hidden`}>
                {m.breedImage ? (
                  <img src={m.breedImage} alt={m.breedName} className="w-full h-full object-cover" />
                ) : (
                  m.breedEmoji
                )}
              </div>
            </div>
            <div className="mt-8 flex flex-wrap gap-3 justify-center">
              {!m.shared ? (
                <button onClick={() => shareMatch(m.id)} className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-5 py-2">📣 Share to gallery</button>
              ) : (
                <span className="btn-pop bg-mint px-5 py-2">✅ Shared</span>
              )}
              <a
                href={`data:text/plain,${encodeURIComponent(`I am a ${m.breedName} — ${m.trait} · via dogppleganger`)}`}
                download={`${m.breedName}.txt`}
                className="btn-pop btn-pop-hover bg-card px-5 py-2"
              >⬇️ Download</a>
              <button
                onClick={() => { discardMatch(m.id); router.navigate({ to: "/upload" }); }}
                className="btn-pop btn-pop-hover bg-card px-5 py-2"
              >🗑️ Discard</button>
              <Link to="/upload" className="btn-pop btn-pop-hover bg-sunshine px-5 py-2">🔁 Try another</Link>
            </div>
          </>
        )}
      </div>
    </AppShell>
  );
}
