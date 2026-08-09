import { Link, useNavigate } from "react-router-dom";
import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { useStore } from "@/lib/store";

export default Signup;

function Signup() {
  const { signup } = useStore();
  const navigate = useNavigate();
  const [u, setU] = useState("");
  const [e, setE] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState("");
  return (
    <AppShell>
      <div className="max-w-md mx-auto card-pop p-8">
        <div className="text-5xl">🐾</div>
        <h1 className="font-display text-3xl font-black mt-1">Make an account</h1>
        <p className="text-muted-foreground text-sm">
          Save your matches, join the pack, get notified.
        </p>
        <form
          className="mt-6 space-y-3"
          onSubmit={(ev) => {
            ev.preventDefault();
            if (!u || !e || !p) {
              setErr("Fill everything, pup.");
              return;
            }
            signup(u.trim(), e.trim(), p);
            navigate("/upload");
          }}
        >
          <Field label="Username" value={u} onChange={setU} placeholder="mooncorgi" />
          <Field label="Email" value={e} onChange={setE} placeholder="you@dog.dog" type="email" />
          <Field label="Password" value={p} onChange={setP} type="password" placeholder="••••••" />
          {err && <div className="text-destructive text-sm">{err}</div>}
          <button className="btn-pop btn-pop-hover bg-primary text-primary-foreground w-full py-3 text-lg mt-2">
            Create my dog profile
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

function Field({
  label,
  ...p
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  placeholder?: string;
}) {
  return (
    <label className="block">
      <span className="text-sm font-bold">{label}</span>
      <input
        type={p.type ?? "text"}
        value={p.value}
        placeholder={p.placeholder}
        onChange={(e) => p.onChange(e.target.value)}
        className="mt-1 w-full rounded-xl border-2 border-[var(--ink)] px-3 py-2 bg-card focus:outline-none focus:ring-2 focus:ring-primary"
      />
    </label>
  );
}
