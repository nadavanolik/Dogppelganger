import { createFileRoute, Link } from "@tanstack/react-router";
import { AppShell, RequireAuth } from "@/components/AppShell";
import { useStore } from "@/lib/store";

export const Route = createFileRoute("/notifications")({ component: NotifPage });

function NotifPage() { return <AppShell><RequireAuth><Inner /></RequireAuth></AppShell>; }

function Inner() {
  const { state, markAllRead } = useStore();
  const me = state.user!;
  const mine = state.notifications.filter((n) => n.userId === me.id);
  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <h1 className="font-display text-4xl font-black">Notifications</h1>
        <button onClick={markAllRead} className="btn-pop btn-pop-hover bg-card px-3 py-1 text-sm">Mark all read</button>
      </div>
      <div className="space-y-2">
        {mine.length === 0 && <div className="card-pop p-8 text-center text-muted-foreground">Quiet in here. Go bark somewhere.</div>}
        {mine.map((n) => (
          <Link key={n.id} to={n.href ?? "/"} className={`card-pop-sm p-4 flex items-center gap-3 hover:-translate-y-0.5 transition ${n.read ? "opacity-70" : ""}`}>
            <div className="text-2xl">{n.kind === "match" ? "🐕" : n.kind === "dm" ? "💌" : "❤️"}</div>
            <div className="flex-1">
              <div className="font-bold">{n.text}</div>
              <div className="text-xs text-muted-foreground">{new Date(n.at).toLocaleString()}</div>
            </div>
            {!n.read && <span className="h-3 w-3 rounded-full bg-primary border-2 border-[var(--ink)]" />}
          </Link>
        ))}
      </div>
    </div>
  );
}
