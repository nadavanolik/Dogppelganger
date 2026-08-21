import { Link, useNavigate } from "react-router-dom";
import { useState } from "react";

import { AppShell } from "@/components/AppShell";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default Signup;

// Mirrors the server's rule in backend/app/security.py. bcrypt hashes at most
// 72 bytes and silently ignores the rest, so a longer password would be a
// promise the hash can't keep — the server rejects it rather than truncating,
// and saying so here saves a round trip.
const MIN_PASSWORD = 8;

function Signup() {
  const { signup } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    setError("");
    if (password.length < MIN_PASSWORD) {
      setError(`Password must be at least ${MIN_PASSWORD} characters.`);
      return;
    }
    if (password !== confirm) {
      setError("Those two passwords don't match.");
      return;
    }
    setBusy(true);
    try {
      await signup(email, username, password);
      navigate("/profile", { replace: true });
    } catch (err) {
      // 409 means the email or username is taken; the server's wording is
      // already the right thing to show.
      setError(err instanceof ApiError ? err.message : "Couldn't create that account.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell>
      <div className="max-w-md mx-auto card-pop p-8">
        <div className="text-5xl">🐶</div>
        <h1 className="font-display text-3xl font-black mt-1">Join the pack</h1>
        <p className="text-muted-foreground text-sm">
          Your photos stay private unless you share them.
        </p>
        <form className="mt-6 space-y-3" onSubmit={submit}>
          <label className="block">
            <span className="text-sm font-bold">Username</span>
            <input
              value={username}
              onChange={(x) => setUsername(x.target.value)}
              autoComplete="username"
              required
              maxLength={80}
              className="mt-1 w-full rounded-xl border-2 border-[var(--ink)] px-3 py-2 bg-card"
              placeholder="moodyoak"
            />
          </label>
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
              autoComplete="new-password"
              required
              className="mt-1 w-full rounded-xl border-2 border-[var(--ink)] px-3 py-2 bg-card"
              placeholder={`at least ${MIN_PASSWORD} characters`}
            />
          </label>
          <label className="block">
            <span className="text-sm font-bold">Confirm password</span>
            <input
              value={confirm}
              onChange={(x) => setConfirm(x.target.value)}
              type="password"
              autoComplete="new-password"
              required
              className="mt-1 w-full rounded-xl border-2 border-[var(--ink)] px-3 py-2 bg-card"
            />
          </label>
          {error && <div className="text-destructive text-sm">{error}</div>}
          <button
            disabled={busy}
            className="btn-pop btn-pop-hover bg-primary text-primary-foreground w-full py-3 text-lg disabled:opacity-60"
          >
            {busy ? "Creating…" : "Create account"}
          </button>
        </form>
        <div className="mt-4 text-sm text-muted-foreground">
          Already have one?{" "}
          <Link to="/login" className="underline font-bold">
            Log in
          </Link>
        </div>
      </div>
    </AppShell>
  );
}
