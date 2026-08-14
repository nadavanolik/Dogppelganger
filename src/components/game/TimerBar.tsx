import { useLayoutEffect, useRef } from "react";

import { useSecondsLeft } from "@/lib/useCountdown";

/**
 * The question countdown.
 *
 * The bar is **anchored to the server's deadline**, not animated from React: on
 * each new question we jump the fill to wherever the clock actually is, then
 * hand the browser a single `width 0%` transition lasting exactly as long as the
 * time remaining. The browser interpolates against its own clock, so the bar
 * lands on empty at the same moment the server closes the question.
 *
 * Driving the width from state on every animation frame looked equivalent and
 * wasn't: the paint then depends on how fast React can re-render, and drifts out
 * of step with the real clock when frames are throttled — a background window, a
 * busy dev build — leaving the bar half full with seconds left on it.
 *
 * `serverNow` comes from the room socket and corrects for clock skew, so every
 * player's bar drains together even if their laptop clock is minutes off.
 */
export function TimerBar({
  endsAt,
  durationMs,
  serverNow,
  label,
}: {
  endsAt: number | null;
  durationMs: number;
  serverNow: () => number;
  label?: string;
}) {
  const seconds = useSecondsLeft(endsAt, serverNow);
  const fill = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const el = fill.current;
    if (!el) return;

    const remaining = endsAt ? Math.max(0, endsAt - serverNow()) : 0;
    const startRatio = durationMs > 0 ? Math.min(1, remaining / durationMs) : 0;

    // Snap to the true position first — no transition, so a late joiner or a
    // reconnect picks up mid-drain instead of sliding in from full.
    el.style.transition = "none";
    el.style.width = `${startRatio * 100}%`;
    void el.offsetWidth; // force a reflow so the change below actually animates

    el.style.transition = `width ${remaining}ms linear`;
    el.style.width = "0%";
  }, [endsAt, durationMs, serverNow]);

  const ratio = durationMs > 0 ? Math.min(1, (seconds * 1000) / durationMs) : 0;
  const colour =
    ratio > 0.5 ? "var(--mint)" : ratio > 0.2 ? "var(--sunshine)" : "var(--destructive)";

  return (
    <div>
      <div className="flex items-center justify-between text-sm font-bold">
        <span className="text-muted-foreground">{label}</span>
        <span aria-live="off">{seconds}s</span>
      </div>
      <div
        className="mt-1 h-4 rounded-full border-2 border-[var(--ink)] overflow-hidden bg-card"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={Math.round(durationMs / 1000)}
        aria-valuenow={seconds}
      >
        <div ref={fill} className="h-full" style={{ backgroundColor: colour }} />
      </div>
    </div>
  );
}
