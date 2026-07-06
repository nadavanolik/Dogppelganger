import { createFileRoute, Link, useRouter } from "@tanstack/react-router";
import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { useStore } from "@/lib/store";

export const Route = createFileRoute("/login")({ component: Login });

function Login() {
  const { login, state } = useStore();
  const router = useRouter();
  const [e, setE] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState("");
  return (
    <AppShell>
      <div className="max-w-md mx-auto card-pop p-8">
        <div className="text-5xl">🐕</div>
        <h1 className="font-display text-3xl font-black mt-1">Welcome back</h1>
        <p className="text-muted-foreground text-sm">Prototype: any password works if the email matches a seeded or created account.</p>
        <form
          className="mt-6 space-y-3"
          onSubmit={(ev) => {
            ev.preventDefault();
            const u = login(e, p);
            if (!u) { setErr("No dog with that email."); return; }
            router.navigate({ to: "/dashboard" });
          }}
        >
          <label className="block">
            <span className="text-sm font-bold">Email</span>
            <input value={e} onChange={(x) => setE(x.target.value)} className="mt-1 w-full rounded-xl border-2 border-[var(--ink)] px-3 py-2 bg-card" placeholder="oak@dog.dog" />
          </label>
          <label className="block">
            <span className="text-sm font-bold">Password</span>
            <input value={p} onChange={(x) => setP(x.target.value)} type="password" className="mt-1 w-full rounded-xl border-2 border-[var(--ink)] px-3 py-2 bg-card" placeholder="anything" />
          </label>
          {err && <div className="text-destructive text-sm">{err}</div>}
          <button className="btn-pop btn-pop-hover bg-primary text-primary-foreground w-full py-3 text-lg">Log in</button>
        </form>
        <div className="mt-4 text-sm text-muted-foreground">
          Try one of: {state.users.map((u) => (
            <button key={u.id} type="button" onClick={() => setE(u.email)} className="underline font-bold mx-1">{u.email}</button>
          ))}
        </div>
        <div className="mt-2 text-sm text-muted-foreground">New? <Link to="/signup" className="underline font-bold">Sign up</Link></div>
      </div>
    </AppShell>
  );
}
