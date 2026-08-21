import { useNavigate } from "react-router-dom";
import { useState } from "react";

import { AppShell } from "@/components/AppShell";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { userApi } from "@/lib/dmApi";

export default Settings;

function Settings() {
  const { user, refresh, adoptTokens, logout } = useAuth();
  const navigate = useNavigate();
  if (!user) return null;

  return (
    <AppShell>
      <div className="max-w-2xl mx-auto space-y-6">
        <div>
          <h1 className="font-display text-4xl font-black">Account settings</h1>
          <p className="text-muted-foreground">Signed in as @{user.username}</p>
        </div>
        <ProfileCard onSaved={refresh} />
        <PasswordCard onChanged={adoptTokens} />
        <DangerCard
          onDeleted={() => {
            logout();
            navigate("/", { replace: true });
          }}
        />
      </div>
    </AppShell>
  );
}

function Feedback({ error, ok }: { error: string; ok: string }) {
  if (error) return <div className="text-destructive text-sm">{error}</div>;
  if (ok) return <div className="text-sm text-muted-foreground">{ok}</div>;
  return null;
}

function ProfileCard({ onSaved }: { onSaved: () => Promise<void> }) {
  const { user } = useAuth();
  const [username, setUsername] = useState(user?.username ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [currentPassword, setCurrentPassword] = useState("");
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");

  const emailChanged = email.trim().toLowerCase() !== (user?.email ?? "");

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    setError("");
    setOk("");
    try {
      await userApi.updateProfile({
        username,
        email,
        currentPassword: currentPassword || undefined,
      });
      await onSaved();
      setCurrentPassword("");
      setOk("Saved.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save that.");
    }
  }

  return (
    <form onSubmit={submit} className="card-pop p-6 space-y-3">
      <div className="font-display text-xl font-black">Profile</div>
      <p className="text-sm text-muted-foreground">
        Changing your username updates it everywhere you've posted — the name is stored in one place
        now, not copied onto every post.
      </p>
      <label className="block">
        <span className="text-sm font-bold">Username</span>
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="mt-1 w-full rounded-xl border-2 border-[var(--ink)] px-3 py-2 bg-card"
        />
      </label>
      <label className="block">
        <span className="text-sm font-bold">Email</span>
        <input
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          type="email"
          className="mt-1 w-full rounded-xl border-2 border-[var(--ink)] px-3 py-2 bg-card"
        />
      </label>
      {emailChanged && (
        <label className="block">
          <span className="text-sm font-bold">Current password</span>
          {/* Required for an email change, not for a username one: the email is
              the login identifier, so changing it is close to changing who owns
              the account. */}
          <input
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            type="password"
            autoComplete="current-password"
            className="mt-1 w-full rounded-xl border-2 border-[var(--ink)] px-3 py-2 bg-card"
            placeholder="needed to change your email"
          />
        </label>
      )}
      <Feedback error={error} ok={ok} />
      <button className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-5 py-2">
        Save
      </button>
    </form>
  );
}

function PasswordCard({ onChanged }: { onChanged: (tokens: never) => void }) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    setError("");
    setOk("");
    if (newPassword !== confirm) {
      setError("Those two passwords don't match.");
      return;
    }
    try {
      const tokens = await userApi.changePassword(currentPassword, newPassword);
      // The server invalidates every token issued before now and hands back a
      // fresh pair, so this tab survives while other devices are logged out.
      onChanged(tokens as never);
      setCurrentPassword("");
      setNewPassword("");
      setConfirm("");
      setOk("Password changed. Any other device you were signed in on has been logged out.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't change your password.");
    }
  }

  return (
    <form onSubmit={submit} className="card-pop p-6 space-y-3">
      <div className="font-display text-xl font-black">Password</div>
      <label className="block">
        <span className="text-sm font-bold">Current password</span>
        <input
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
          type="password"
          autoComplete="current-password"
          className="mt-1 w-full rounded-xl border-2 border-[var(--ink)] px-3 py-2 bg-card"
        />
      </label>
      <label className="block">
        <span className="text-sm font-bold">New password</span>
        <input
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          type="password"
          autoComplete="new-password"
          className="mt-1 w-full rounded-xl border-2 border-[var(--ink)] px-3 py-2 bg-card"
        />
      </label>
      <label className="block">
        <span className="text-sm font-bold">Confirm new password</span>
        <input
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          type="password"
          autoComplete="new-password"
          className="mt-1 w-full rounded-xl border-2 border-[var(--ink)] px-3 py-2 bg-card"
        />
      </label>
      <Feedback error={error} ok={ok} />
      <button className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-5 py-2">
        Change password
      </button>
    </form>
  );
}

function DangerCard({ onDeleted }: { onDeleted: () => void }) {
  const { user } = useAuth();
  const [password, setPassword] = useState("");
  const [typed, setTyped] = useState("");
  const [error, setError] = useState("");
  const confirmed = typed === user?.username;

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    setError("");
    try {
      await userApi.deleteAccount(password);
      onDeleted();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't delete your account.");
    }
  }

  return (
    <form onSubmit={submit} className="card-pop p-6 space-y-3 border-destructive">
      <div className="font-display text-xl font-black text-destructive">Delete account</div>
      {/* Spelled out because it is not the obvious behaviour, and a vaguer
          version would read as a dark pattern once someone noticed their posts
          were still there. */}
      <p className="text-sm text-muted-foreground">
        Your photos, matches and reactions are erased, including any photos or videos you sent in
        chats. Posts, comments and messages you sent stay where they are, credited to{" "}
        <b>[deleted user]</b>, so conversations other people took part in still make sense. Your
        username and email become available again. This cannot be undone.
      </p>
      <label className="block">
        <span className="text-sm font-bold">Password</span>
        <input
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          type="password"
          autoComplete="current-password"
          className="mt-1 w-full rounded-xl border-2 border-[var(--ink)] px-3 py-2 bg-card"
        />
      </label>
      <label className="block">
        <span className="text-sm font-bold">
          Type <code>{user?.username}</code> to confirm
        </span>
        <input
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          className="mt-1 w-full rounded-xl border-2 border-[var(--ink)] px-3 py-2 bg-card"
        />
      </label>
      {error && <div className="text-destructive text-sm">{error}</div>}
      <button
        disabled={!confirmed || !password}
        className="btn-pop btn-pop-hover bg-destructive text-destructive-foreground px-5 py-2 disabled:opacity-50"
      >
        Delete my account
      </button>
    </form>
  );
}
