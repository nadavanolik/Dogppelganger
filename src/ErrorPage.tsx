import { useRouteError } from "react-router-dom";

import { LogoBadge } from "@/components/LogoBadge";

// Rendered by the router when a route throws during render.
// Standalone (no store/AppShell) since the error may have come from them.
export default function ErrorPage() {
  const error = useRouteError() as Error | undefined;
  console.error(error);

  return (
    <div className="relative min-h-screen flex items-center justify-center px-4">
      {/* AppShell is skipped here, so the logo has to come along by hand — a
          plain anchor, not a router Link, since the router may be what broke. */}
      <a href="/" className="absolute top-4 left-4" aria-label="dogppelganger home">
        <LogoBadge />
      </a>
      <div className="card-pop max-w-md p-8 text-center">
        <div className="text-6xl">🙀</div>
        <h1 className="font-display text-2xl font-bold mt-2">Something snapped</h1>
        <p className="mt-2 text-muted-foreground text-sm">{error?.message ?? "Unknown error"}</p>
        <div className="mt-4 flex gap-2 justify-center">
          <button
            onClick={() => window.location.reload()}
            className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-4 py-2"
          >
            Reload
          </button>
          <a href="/" className="btn-pop btn-pop-hover bg-card px-4 py-2">
            Home
          </a>
        </div>
      </div>
    </div>
  );
}
