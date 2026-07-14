import { Link, useRouter } from "@tanstack/react-router";
import { useState, type ReactNode } from "react";
import { useStore } from "@/lib/store";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export function AppShell({ children }: { children: ReactNode }) {
  const { state, logout, markAllRead } = useStore();
  const router = useRouter();
  const [openNotif, setOpenNotif] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const me = state.user;
  const myNotifs = me ? state.notifications.filter((n) => n.userId === me.id) : [];
  const unread = myNotifs.filter((n) => !n.read).length;
  const unreadDMs = myNotifs.filter((n) => n.kind === "dm" && !n.read).length;

  return (
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-40 border-b-2 border-[var(--ink)] bg-background/90 backdrop-blur">
        <div className="mx-auto max-w-7xl px-4 py-3 flex items-center gap-3">
          <Link to="/" className="flex items-center gap-2 shrink-0">
            <div className="h-10 w-10 rounded-full bg-primary border-2 border-[var(--ink)] flex items-center justify-center text-xl shadow-pop-sm">🐶</div>
            <span className="font-display text-2xl font-black tracking-tight hidden sm:inline">dogpelganger</span>
          </Link>

          {me && (
            <nav className="hidden md:flex ml-6 gap-1 items-center">
              <NavLink to="/upload" label="🐕 Match" />
              <NavLink to="/gallery" label="🖼 Gallery" />
              <NavLink to="/forum" label="💬 Forum" />
              <NavLink to="/play" label="🎮 Play" />
            </nav>
          )}

          <div className="ml-auto flex items-center gap-2">
            {me ? (
              <>
                {/* DMs */}
                <Link
                  to="/messages"
                  className="btn-pop btn-pop-hover bg-card px-3 py-1.5 text-sm relative"
                  aria-label="Messages"
                >
                  💌
                  {unreadDMs > 0 && (
                    <span className="absolute -top-1 -right-1 inline-flex items-center justify-center rounded-full bg-primary text-primary-foreground text-[10px] h-4 min-w-4 px-1 border border-[var(--ink)]">
                      {unreadDMs}
                    </span>
                  )}
                </Link>

                {/* Notifications */}
                <div className="relative">
                  <button
                    onClick={() => {
                      setOpenNotif((v) => !v);
                      if (!openNotif) setTimeout(markAllRead, 500);
                    }}
                    className="btn-pop btn-pop-hover bg-sunshine px-3 py-1.5 text-sm"
                    aria-label="Notifications"
                  >
                    🔔 {unread > 0 && <span className="ml-1 inline-flex items-center justify-center rounded-full bg-primary text-primary-foreground text-xs h-5 min-w-5 px-1">{unread}</span>}
                  </button>
                  {openNotif && (
                    <div className="absolute right-0 mt-2 w-80 card-pop p-2 max-h-96 overflow-auto z-50">
                      <div className="flex items-center justify-between px-2 py-1">
                        <div className="font-display font-bold">Notifications</div>
                        <Link to="/notifications" className="text-xs underline" onClick={() => setOpenNotif(false)}>see all</Link>
                      </div>
                      {myNotifs.length === 0 && <div className="p-3 text-sm text-muted-foreground">No news yet. Go make some dogs.</div>}
                      {myNotifs.slice(0, 8).map((n) => (
                        <button
                          key={n.id}
                          onClick={() => {
                            setOpenNotif(false);
                            if (n.href) router.navigate({ to: n.href });
                          }}
                          className="w-full text-left px-2 py-2 rounded-lg hover:bg-muted flex gap-2"
                        >
                          <span>{n.kind === "match" ? "🐕" : n.kind === "dm" ? "💌" : "❤️"}</span>
                          <span className="text-sm">{n.text}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                {/* Avatar menu */}
                <DropdownMenu>
                  <DropdownMenuTrigger className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-mint border-2 border-[var(--ink)] shadow-pop-sm outline-none">
                    <span>🧑</span>
                    <span className="text-sm font-bold hidden sm:inline">@{me.username}</span>
                    <span className="text-xs">▾</span>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="border-2 border-[var(--ink)] shadow-pop-sm">
                    <DropdownMenuLabel>@{me.username}</DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={() => router.navigate({ to: "/profile" })}>🐕 My profile & dogs</DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={() => { logout(); router.navigate({ to: "/" }); }}>
                      🚪 Log out
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>

                {/* Mobile toggle */}
                <button
                  className="md:hidden btn-pop bg-card px-3 py-1.5 text-sm"
                  onClick={() => setMobileNav((v) => !v)}
                  aria-label="Menu"
                >
                  ☰
                </button>
              </>
            ) : (
              <>
                <Link to="/login" className="btn-pop btn-pop-hover bg-card px-4 py-1.5 text-sm">Log in</Link>
                <Link to="/signup" className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-4 py-1.5 text-sm">Sign up</Link>
              </>
            )}
          </div>
        </div>

        {me && mobileNav && (
          <div className="md:hidden border-t border-[var(--ink)]/20 px-4 py-3 grid grid-cols-2 gap-2 bg-background">
            {([
              { to: "/upload", label: "🐕 Match" },
              { to: "/gallery", label: "🖼 Gallery" },
              { to: "/forum", label: "💬 Forum" },
              { to: "/play", label: "🎮 Play" },
              { to: "/messages", label: "💌 Messages" },
              { to: "/profile", label: "👤 Profile" },
            ] as const).map((n) => (
              <Link
                key={n.to}
                to={n.to}
                onClick={() => setMobileNav(false)}
                className="btn-pop bg-card px-3 py-2 text-sm text-center"
              >
                {n.label}
              </Link>
            ))}
          </div>
        )}
      </header>
      <main className="flex-1 mx-auto w-full max-w-7xl px-4 py-8">{children}</main>
      <footer className="border-t-2 border-[var(--ink)] py-6 text-center text-sm text-muted-foreground">
        Made with 🐾 · dogpelganger prototype
      </footer>
    </div>
  );
}

function NavLink({ to, label }: { to: string; label: string }) {
  return (
    <Link
      to={to}
      className="px-3 py-1.5 rounded-full text-sm font-bold hover:bg-sunshine transition"
      activeProps={{ className: "px-3 py-1.5 rounded-full text-sm font-bold bg-primary text-primary-foreground border-2 border-[var(--ink)]" }}
    >
      {label}
    </Link>
  );
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { state } = useStore();
  if (!state.user) {
    return (
      <div className="card-pop max-w-md mx-auto p-8 text-center">
        <div className="text-5xl mb-2">🐕‍🦺</div>
        <h2 className="font-display text-2xl font-bold">Only signed-in dogs beyond this point</h2>
        <p className="text-muted-foreground mt-1">Log in or make an account to continue.</p>
        <div className="mt-4 flex gap-2 justify-center">
          <Link to="/login" className="btn-pop btn-pop-hover bg-card px-4 py-2">Log in</Link>
          <Link to="/signup" className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-4 py-2">Sign up</Link>
        </div>
      </div>
    );
  }
  return <>{children}</>;
}
