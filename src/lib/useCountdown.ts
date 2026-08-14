import { useEffect, useState } from "react";

// Fast enough that the number never looks stuck, slow enough to be free.
const TICK_MS = 200;

/**
 * Whole seconds left until a deadline.
 *
 * `now` is injected rather than assumed to be `Date.now`, because the game's
 * deadlines come from the server: the room socket supplies a `serverNow` that
 * corrects for clock skew so every player's countdown agrees.
 *
 * Deliberately a coarse interval, not an animation frame. Anything that needs
 * to move smoothly should be handed the deadline and animated by CSS (see
 * `TimerBar`) — driving pixels from React state 60 times a second makes the
 * visuals hostage to render speed.
 */
export function useSecondsLeft(endsAt: number | null, now: () => number): number {
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    if (!endsAt) {
      setSeconds(0);
      return;
    }
    const read = () => setSeconds(Math.max(0, Math.ceil((endsAt - now()) / 1000)));
    read();
    const id = window.setInterval(read, TICK_MS);
    return () => window.clearInterval(id);
  }, [endsAt, now]);

  return seconds;
}
