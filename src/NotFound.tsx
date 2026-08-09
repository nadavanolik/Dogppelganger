import { Link } from "react-router-dom";
import { AppShell } from "@/components/AppShell";

export default function NotFound() {
  return (
    <AppShell>
      <div className="card-pop max-w-md mx-auto p-8 text-center">
        <div className="text-7xl mb-2">🐕‍🦺</div>
        <h1 className="font-display text-4xl font-black">Lost puppy</h1>
        <p className="mt-2 text-muted-foreground">This page ran off. Let's go home.</p>
        <Link
          to="/"
          className="btn-pop btn-pop-hover bg-primary text-primary-foreground inline-block mt-6 px-5 py-2"
        >
          Back to home
        </Link>
      </div>
    </AppShell>
  );
}
