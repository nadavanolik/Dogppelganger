import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useState } from "react";

import { AppShell } from "@/components/AppShell";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default Login;

function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(email, password);
      // Back to wherever the guard interrupted you, or your profile.
      const returnTo = params.get("return_to");
      navigate(returnTo && returnTo.startsWith("/") ? returnTo : "/profile", { replace: true });
    } catch (err) {
      // The server answers "invalid credentials" for a wrong password and an
      // unknown email alike, on purpose — two different messages would let
      // anyone check which addresses have accounts.
      setError(err instanceof ApiError ? err.message : "Couldn't log you in.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell>
      <div className="max-w-md mx-auto card-pop p-8">
        <div className="text-5xl">🐕</div>
        <h1 className="font-display text-3xl font-black mt-1">Welcome back</h1>
        <p className="text-muted-foreground text-sm">Log in to find your dog again.</p>
        <form className="mt-6 space-y-3" onSubmit={submit}>
          <label className="block">
            <span className="text-sm font-bold">Email</span>
            <input
              value={email}
              onChange={(x) => setEmail(x.target.value)}
              type="email"
              autoComplete="email"
              required
              className="mt-1 w-full rounded-xl border-2 border-[var(--ink)] px-3 py-2 bg-card"
              placeholder="you@example.com"
            />
          </label>
          <label className="block">
            <span className="text-sm font-bold">Password</span>
            <input
              value={password}
              onChange={(x) => setPassword(x.target.value)}
              type="password"
              autoComplete="current-password"
              required
              className="mt-1 w-full rounded-xl border-2 border-[var(--ink)] px-3 py-2 bg-card"
            />
          </label>
          {error && <div className="text-destructive text-sm">{error}</div>}
          <button
            disabled={busy}
            className="btn-pop btn-pop-hover bg-primary text-primary-foreground w-full py-3 text-lg disabled:opacity-60"
          >
            {busy ? "Logging in…" : "Log in"}
          </button>
        </form>
        <div className="mt-4 text-sm text-muted-foreground">
          New?{" "}
          <Link to="/signup" className="underline font-bold">
            Sign up
          </Link>
        </div>
      </div>
    </AppShell>
  );
}
