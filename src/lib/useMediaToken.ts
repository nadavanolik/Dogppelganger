/**
 * The current short-lived media token, as React state.
 *
 * `api.ts` holds it in a module variable so that plain modules can read it, but
 * a WebSocket has to *reconnect* when it changes — so the socket hooks need it
 * as a value that triggers an effect, not a getter they happen to call at the
 * right moment.
 *
 * It is polled rather than pushed because the token is re-minted on a timer
 * inside AuthProvider; a subscription would be more machinery than a value that
 * changes twice an hour deserves.
 */
import { useEffect, useState } from "react";

import { getMediaToken } from "./api";

export function useMediaToken(): string | null {
  const [token, setToken] = useState<string | null>(() => getMediaToken());

  useEffect(() => {
    const check = () => {
      const current = getMediaToken();
      setToken((previous) => (previous === current ? previous : current));
    };
    check();
    const timer = window.setInterval(check, 2000);
    return () => window.clearInterval(timer);
  }, []);

  return token;
}
