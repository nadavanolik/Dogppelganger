/**
 * Route-level guards.
 *
 * These replace the `RequireAuth` card that used to be dropped inside three of
 * eighteen pages. That version rendered a "please log in" panel in place of the
 * content but never redirected and never remembered where you were going —
 * and, worse, the pages it did *not* wrap fell back to acting as the first
 * seeded mock account, so a logged-out visitor silently browsed as somebody.
 */
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "@/lib/auth";

/**
 * Everything behind a login.
 *
 * The `loading` case renders nothing rather than redirecting. On a hard refresh
 * the token is in localStorage but `/api/auth/me` hasn't answered yet, so
 * treating "not yet known" as "not logged in" would bounce a signed-in user to
 * the login page on every reload.
 */
export function Protected() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") return null;
  if (status === "anon") {
    const returnTo = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?return_to=${returnTo}`} replace />;
  }
  return <Outlet />;
}

/** Login and signup: pointless once you're already signed in. */
export function PublicOnly() {
  const { status } = useAuth();

  if (status === "loading") return null;
  if (status === "authed") return <Navigate to="/profile" replace />;
  return <Outlet />;
}
