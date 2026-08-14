import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { HumanFace } from "@/components/game/HumanFace";
import { dogSrc } from "@/lib/dogSrc";
import type { Claim, MatchBoard as BoardData, PairMap } from "@/lib/gameApi";
import { playerColor, playerColorSoft } from "@/lib/playerColor";

/**
 * The Mix & Match board: four humans on the left, four dogs on the right, and a
 * line for every pairing anyone has claimed.
 *
 * Shared by both modes. In solo the only claims are yours; in a room every
 * player's are drawn in their own colour, which is the whole point — you can see
 * someone commit to a pairing and it tells you something.
 *
 * **Nothing here is optimistic.** A tap you've sent but the server hasn't
 * confirmed is drawn dashed and marked "pending"; it only becomes a real line
 * when it comes back in `claims`. Painting it as fact first would mean showing a
 * state the server might be about to reject, which is exactly the divergence the
 * whole design is trying to avoid.
 */

type Point = { x: number; y: number };

export function MatchBoard({
  board,
  claims,
  meId,
  answer = null,
  pending = {},
  disabled = false,
  onClaim,
  onRelease,
}: {
  board: BoardData;
  claims: Claim[];
  meId: string;
  /** human slot -> dog slot, once the round is closed. */
  answer?: PairMap | null;
  /** Claims sent and not yet answered by the server. */
  pending?: Record<number, number>;
  disabled?: boolean;
  onClaim: (human: number, dog: number) => void;
  onRelease: (human: number) => void;
}) {
  const wrap = useRef<HTMLDivElement>(null);
  const humanEls = useRef<(HTMLButtonElement | null)[]>([]);
  const dogEls = useRef<(HTMLButtonElement | null)[]>([]);
  const [anchors, setAnchors] = useState<{ humans: Point[]; dogs: Point[] }>({
    humans: [],
    dogs: [],
  });
  const [picked, setPicked] = useState<{ side: "human" | "dog"; slot: number } | null>(null);

  const revealing = answer !== null;
  const mine = new Map<number, number>();
  for (const claim of claims) if (claim.playerId === meId) mine.set(claim.human, claim.dog);

  // ------------------------------------------------------- line geometry

  const measure = useCallback(() => {
    const box = wrap.current?.getBoundingClientRect();
    if (!box) return;
    const edge = (el: HTMLElement | null, side: "left" | "right"): Point => {
      if (!el) return { x: 0, y: 0 };
      const r = el.getBoundingClientRect();
      return {
        x: (side === "right" ? r.right : r.left) - box.left,
        y: r.top + r.height / 2 - box.top,
      };
    };
    setAnchors({
      humans: board.humans.map((_, i) => edge(humanEls.current[i], "right")),
      dogs: board.dogs.map((_, i) => edge(dogEls.current[i], "left")),
    });
  }, [board]);

  // Lines are drawn from measured positions, so anything that moves a tile —
  // a resize, a font swap, a photo finally decoding — has to re-measure.
  useLayoutEffect(() => {
    measure();
    const observer = new ResizeObserver(measure);
    if (wrap.current) observer.observe(wrap.current);
    window.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [measure]);

  // ---------------------------------------------------------- interaction

  const pair = useCallback(
    (human: number, dog: number) => {
      setPicked(null);
      if (mine.get(human) === dog) onRelease(human);
      else onClaim(human, dog);
    },
    // `mine` is rebuilt each render from props; the callback only reads it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [onClaim, onRelease, claims, meId],
  );

  const tap = useCallback(
    (side: "human" | "dog", slot: number) => {
      if (disabled) return;
      if (picked?.side === side && picked.slot === slot) {
        setPicked(null); // tapping the same tile twice backs out
      } else if (picked && picked.side !== side) {
        const human = side === "human" ? slot : picked.slot;
        const dog = side === "dog" ? slot : picked.slot;
        pair(human, dog);
      } else {
        setPicked({ side, slot });
      }
    },
    [disabled, picked, pair],
  );

  // Submitting or the round closing drops the selection — otherwise a person
  // stays ringed and dogs stay locked on a board you can no longer touch.
  useEffect(() => {
    if (disabled) setPicked(null);
  }, [disabled]);

  // Tapping anywhere that isn't a button puts the tile back down. Without this
  // a stray tap leaves a person selected and the 🔒 overlays hanging on dogs
  // that are perfectly available for every other person.
  useEffect(() => {
    if (picked === null) return;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as HTMLElement | null;
      if (!target?.closest("button")) setPicked(null);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [picked]);

  useEffect(() => {
    if (disabled) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") return setPicked(null);
      const index = Number(event.key) - 1;
      if (!Number.isInteger(index) || index < 0 || index > 3) return;
      event.preventDefault();
      // Numbers pick a person first, then a dog — the order you'd say it aloud.
      tap(picked === null ? "human" : "dog", index);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [disabled, picked, tap]);

  // What's out of reach for the tile currently in hand — the exclusivity rule,
  // shown before you tap rather than as a rejection afterwards. Both directions,
  // because you can start from either column.
  const held = (side: "human" | "dog", slot: number) =>
    new Map(
      claims
        .filter((c) => c.playerId !== meId && (side === "human" ? c.human : c.dog) === slot)
        .map((c) => [side === "human" ? c.dog : c.human, c] as const),
    );
  const empty = new Map<number, Claim>();
  const blockedDogs = picked?.side === "human" ? held("human", picked.slot) : empty;
  const blockedHumans = picked?.side === "dog" ? held("dog", picked.slot) : empty;

  // ---------------------------------------------------------------- lines

  const lines = [
    ...claims.map((claim) => ({
      human: claim.human,
      dog: claim.dog,
      color: lineColor(claim, meId, answer),
      width: claim.playerId === meId ? 6 : 3,
      dashed: false,
      label: claim.playerId === meId ? null : claim.name,
    })),
    ...Object.entries(pending).map(([human, dog]) => ({
      human: Number(human),
      dog,
      color: "var(--muted-foreground)",
      width: 4,
      dashed: true,
      label: null,
    })),
  ];

  return (
    <div ref={wrap} className="relative grid grid-cols-2 gap-10 sm:gap-24">
      <svg
        className="absolute inset-0 h-full w-full pointer-events-none overflow-visible"
        aria-hidden
      >
        {revealing &&
          board.humans.map((human) => {
            const dog = answer?.[String(human.slot)];
            if (dog === undefined) return null;
            return (
              <Line
                key={`truth-${human.slot}`}
                from={anchors.humans[human.slot]}
                to={anchors.dogs[dog]}
                color="var(--ink)"
                width={2}
                dashed
                opacity={0.35}
              />
            );
          })}
        {lines.map((line, i) => (
          <Line
            key={`${line.human}-${line.dog}-${i}`}
            from={anchors.humans[line.human]}
            to={anchors.dogs[line.dog]}
            color={line.color}
            width={line.width}
            dashed={line.dashed}
            label={line.label}
          />
        ))}
      </svg>

      <div className="space-y-3">
        {board.humans.map((human, i) => {
          const claimedDog = mine.get(human.slot) ?? pending[human.slot];
          const right = revealing && answer?.[String(human.slot)] === mine.get(human.slot);
          const taken = blockedHumans.get(human.slot);
          return (
            <button
              key={human.id}
              ref={(el) => {
                humanEls.current[i] = el;
              }}
              type="button"
              disabled={disabled}
              onClick={() => tap("human", human.slot)}
              aria-label={
                taken
                  ? `Person ${i + 1}, claimed with this dog by ${taken.name}`
                  : `Person ${i + 1}${claimedDog !== undefined ? ", matched" : ""}`
              }
              aria-pressed={picked?.side === "human" && picked.slot === human.slot}
              className={`card-pop-sm relative flex w-full items-center gap-2 overflow-hidden p-2 ${
                disabled ? "cursor-default" : "btn-pop-hover cursor-pointer"
              } ${tileRing(
                picked?.side === "human" && picked.slot === human.slot,
                revealing ? right : undefined,
              )}`}
            >
              <HumanFace
                seed={human.humanSeed}
                url={human.humanUrl}
                className="h-14 w-14 sm:h-20 sm:w-20 shrink-0 rounded-xl border-2 border-[var(--ink)]"
              />
              <span className="font-display text-lg font-black">{i + 1}</span>
              {taken && <Locked claim={taken} />}
            </button>
          );
        })}
      </div>

      <div className="space-y-3">
        {board.dogs.map((dog, i) => {
          const taken = blockedDogs.get(dog.slot);
          return (
            <button
              key={dog.slot}
              ref={(el) => {
                dogEls.current[i] = el;
              }}
              type="button"
              disabled={disabled}
              onClick={() => tap("dog", dog.slot)}
              aria-label={taken ? `Dog ${i + 1}, claimed by ${taken.name}` : `Dog ${i + 1}`}
              aria-pressed={picked?.side === "dog" && picked.slot === dog.slot}
              className={`card-pop-sm relative flex w-full items-center justify-end gap-2 overflow-hidden p-2 ${
                disabled ? "cursor-default" : "btn-pop-hover cursor-pointer"
              } ${tileRing(picked?.side === "dog" && picked.slot === dog.slot)}`}
            >
              <span className="font-display text-lg font-black">{i + 1}</span>
              <img
                src={dogSrc(dog.dogIndex)}
                alt=""
                onLoad={measure}
                className="h-14 w-14 sm:h-20 sm:w-20 shrink-0 rounded-xl border-2 border-[var(--ink)] object-cover"
              />
              {taken && <Locked claim={taken} />}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/**
 * Laid over the tile you *can't* combine with the one in your hand.
 *
 * Only this combination is gone — the tile underneath is still free to pair
 * with anything else, which is the rule the whole game turns on.
 */
function Locked({ claim }: { claim: Claim }) {
  return (
    <span
      className="absolute inset-0 grid place-items-center bg-[var(--card)]/80 text-xs font-bold"
      style={{ boxShadow: `inset 0 0 0 4px ${playerColor(claim.playerId)}` }}
    >
      🔒 @{claim.name}
    </span>
  );
}

function lineColor(claim: Claim, meId: string, answer: PairMap | null): string {
  if (answer === null) return playerColor(claim.playerId);
  const right = answer[String(claim.human)] === claim.dog;
  if (claim.playerId !== meId) return right ? playerColorSoft(claim.playerId) : "transparent";
  return right ? "var(--mint)" : "var(--destructive)";
}

function tileRing(selected: boolean, correct?: boolean): string {
  if (correct === true) return "ring-4 ring-[var(--mint)]";
  if (correct === false) return "ring-4 ring-[var(--destructive)]";
  return selected ? "ring-4 ring-[var(--sky)]" : "";
}

function Line({
  from,
  to,
  color,
  width,
  dashed,
  opacity = 1,
  label,
}: {
  from?: Point;
  to?: Point;
  color: string;
  width: number;
  dashed?: boolean;
  opacity?: number;
  label?: string | null;
}) {
  if (!from || !to || color === "transparent") return null;
  // A gentle S-curve rather than a straight line: with up to twelve players'
  // claims on one board, curves stay tellable apart where straight lines overlap.
  const bend = Math.max(24, (to.x - from.x) / 2);
  const path = `M ${from.x} ${from.y} C ${from.x + bend} ${from.y}, ${to.x - bend} ${to.y}, ${to.x} ${to.y}`;
  return (
    <g opacity={opacity}>
      <path
        d={path}
        fill="none"
        stroke={color}
        strokeWidth={width}
        strokeLinecap="round"
        strokeDasharray={dashed ? "6 6" : undefined}
      />
      {label && (
        <text
          x={(from.x + to.x) / 2}
          y={(from.y + to.y) / 2 - 6}
          textAnchor="middle"
          className="fill-[var(--ink)] text-[10px] font-bold"
        >
          @{label}
        </text>
      )}
    </g>
  );
}
