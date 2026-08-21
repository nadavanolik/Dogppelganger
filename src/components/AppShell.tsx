import { Link, NavLink as RouterNavLink, useNavigate } from "react-router-dom";
import { useCallback, useEffect, useState, type ReactNode } from "react";

import { useSocketEvent } from "@/lib/appSocket";
import { useAuth } from "@/lib/auth";
import { dmApi } from "@/lib/dmApi";
import { notificationApi, type Notification } from "@/lib/galleryApi";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export function AppShell({ children }: { children: ReactNode }) {
  const { user: me, logout } = useAuth();
  const navigate = useNavigate();
  const [openNotif, setOpenNotif] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);

  // Two independent badges, because there are two independent things to count.
  // The bell reads the notifications table; the envelope reads unread DMs.
  // Writing a notification row per chat message would double the write volume
  // and give unread two competing sources of truth.
  const [notifs, setNotifs] = useState<Notification[]>([]);
  const [unread, setUnread] = useState(0);
  const [unreadDMs, setUnreadDMs] = useState(0);

  const loadNotifs = useCallback(() => {
    if (!me) return;
    notificationApi
      .list()
      .then((res) => {
        setNotifs(res.items);
        setUnread(res.unread);
      })
      .catch(() => {
        /* the bell is not worth an error banner */
      });
  }, [me]);

  const loadDmCount = useCallback(() => {
    if (!me) return;
    dmApi
      .conversations()
      .then((rows) => setUnreadDMs(rows.reduce((sum, c) => sum + c.unreadCount, 0)))
      .catch(() => {});
  }, [me]);

  useEffect(() => {
    if (!me) {
      setNotifs([]);
      setUnread(0);
      setUnreadDMs(0);
      return;
    }
    loadNotifs();
    loadDmCount();
  }, [me, loadNotifs, loadDmCount]);

  // Live, on the one app-wide socket — the badge moves without a refresh.
  useSocketEvent("notification", loadNotifs);
  useSocketEvent("dm_received", loadDmCount);
  useSocketEvent("dm_read", loadDmCount);

  const markAllRead = useCallback(() => {
    notificationApi
      .markAllRead()
      .then(() => setUnread(0))
      .catch(() => {});
  }, []);

  const myNotifs = notifs;

  return (
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-40 border-b-2 border-[var(--ink)] bg-background/90 backdrop-blur">
        <div className="mx-auto max-w-7xl px-4 py-3 flex items-center gap-3">
          <Link to="/" className="flex items-center gap-2 shrink-0">
            <div className="h-10 w-10 rounded-full bg-primary border-2 border-[var(--ink)] flex items-center justify-center text-xl shadow-pop-sm">
              🐶
            </div>
            <span className="font-display text-2xl font-black tracking-tight hidden sm:inline">
              dogppleganger
            </span>
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
                    🔔{" "}
                    {unread > 0 && (
                      <span className="ml-1 inline-flex items-center justify-center rounded-full bg-primary text-primary-foreground text-xs h-5 min-w-5 px-1">
                        {unread}
                      </span>
                    )}
                  </button>
                  {openNotif && (
                    <div className="absolute right-0 mt-2 w-80 card-pop p-2 max-h-96 overflow-auto z-50">
                      <div className="flex items-center justify-between px-2 py-1">
                        <div className="font-display font-bold">Notifications</div>
                        <Link
                          to="/notifications"
                          className="text-xs underline"
                          onClick={() => setOpenNotif(false)}
                        >
                          see all
                        </Link>
                      </div>
                      {myNotifs.length === 0 && (
                        <div className="p-3 text-sm text-muted-foreground">
                          No news yet. Go make some dogs.
                        </div>
                      )}
                      {myNotifs.slice(0, 8).map((n) => (
                        <button
                          key={n.id}
                          onClick={() => {
                            setOpenNotif(false);
                            if (n.href) navigate(n.href);
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
                  <DropdownMenuContent
                    align="end"
                    className="border-2 border-[var(--ink)] shadow-pop-sm"
                  >
                    <DropdownMenuLabel>@{me.username}</DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={() => navigate("/profile")}>
                      🐕 My profile & dogs
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => navigate("/settings")}>
                      ⚙️ Account settings
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onClick={() => {
                        logout();
                        navigate("/");
                      }}
                    >
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
                <Link to="/login" className="btn-pop btn-pop-hover bg-card px-4 py-1.5 text-sm">
                  Log in
                </Link>
                <Link
                  to="/signup"
                  className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-4 py-1.5 text-sm"
                >
                  Sign up
                </Link>
              </>
            )}
          </div>
        </div>

        {me && mobileNav && (
          <div className="md:hidden border-t border-[var(--ink)]/20 px-4 py-3 grid grid-cols-2 gap-2 bg-background">
            {(
              [
                { to: "/upload", label: "🐕 Match" },
                { to: "/gallery", label: "🖼 Gallery" },
                { to: "/forum", label: "💬 Forum" },
                { to: "/play", label: "🎮 Play" },
                { to: "/messages", label: "💌 Messages" },
                { to: "/profile", label: "👤 Profile" },
              ] as const
            ).map((n) => (
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
        Made with 🐾 · dogppleganger prototype
      </footer>
    </div>
  );
}

function NavLink({ to, label }: { to: string; label: string }) {
  return (
    <RouterNavLink
      to={to}
      className={({ isActive }) =>
        isActive
          ? "px-3 py-1.5 rounded-full text-sm font-bold bg-primary text-primary-foreground border-2 border-[var(--ink)]"
          : "px-3 py-1.5 rounded-full text-sm font-bold hover:bg-sunshine transition"
      }
    >
      {label}
    </RouterNavLink>
  );
}

// `RequireAuth` used to live here: an inline "please log in" card that three of
// eighteen pages wrapped themselves in. It never redirected, never remembered
// where you were headed, and — because the pages that *didn't* use it fell back
// to acting as a seeded mock account — it wasn't really a guard at all. Access
// is now decided once, at the router: see src/components/Guards.tsx.
