import { useMemo } from "react";

/**
 * A cartoon face drawn from a seed string.
 *
 * The game needs a lot of visibly different humans, and there are none stored
 * server-side yet, so the backend sends a seed and we draw. Same seed always
 * draws the same person. When real photos exist the backend fills in `url`
 * instead and this falls through to an <img> — no other code changes.
 *
 * Roughly 6 * 7 * 6 * 6 * 3 * 4 * 5 * 3 combinations, so faces rarely repeat.
 */

const SKIN = ["#f6d5bd", "#eab894", "#d99b6c", "#b97a4c", "#8d5a2f", "#5f3a1f"];
const HAIR = ["#241a12", "#4a2c17", "#8a5a2b", "#c9873a", "#e6c884", "#a8adb3", "#c44a4a"];
const SHIRT = ["#f28b7d", "#7dbdf2", "#8ee0b0", "#f2cf6b", "#c3a0f2", "#f2a0c4"];
const BG = ["#fdeacd", "#dceafa", "#e3f6ea", "#fbe3ef", "#e9e4fb", "#fdf0dd"];

/** Small xorshift PRNG so each feature choice is independent of the others. */
function makeRng(seed: string) {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  let s = h >>> 0 || 1;
  return () => {
    s ^= s << 13;
    s >>>= 0;
    s ^= s >>> 17;
    s ^= s << 5;
    s >>>= 0;
    return s / 4294967296;
  };
}

type Features = {
  skin: string;
  shade: string;
  hair: string;
  shirt: string;
  bg: string;
  hairStyle: number;
  eyes: number;
  mouth: number;
  brows: number;
  accessory: number;
  facialHair: number;
};

function featuresFor(seed: string): Features {
  const rand = makeRng(seed);
  const pick = <T,>(arr: readonly T[]): T => arr[Math.floor(rand() * arr.length)];
  const skinIndex = Math.floor(rand() * SKIN.length);
  return {
    skin: SKIN[skinIndex],
    // Neck and ears sit in shadow: reuse the next tone down.
    shade: SKIN[Math.min(skinIndex + 1, SKIN.length - 1)],
    hair: pick(HAIR),
    shirt: pick(SHIRT),
    bg: pick(BG),
    hairStyle: Math.floor(rand() * 6),
    eyes: Math.floor(rand() * 3),
    mouth: Math.floor(rand() * 4),
    brows: Math.floor(rand() * 3),
    accessory: Math.floor(rand() * 5),
    facialHair: Math.floor(rand() * 3),
  };
}

const INK = "#2a1f19";

function Hair({ f }: { f: Features }) {
  switch (f.hairStyle) {
    case 0: // cropped
      return <path d="M27 44a23 27 0 0 1 46 0c0-14-10-21-23-21S27 30 27 44Z" fill={f.hair} />;
    case 1: // long, past the shoulders
      return (
        <>
          <path d="M24 48c0-20 8-27 26-27s26 7 26 27v28h-9V44H33v32h-9Z" fill={f.hair} />
          <path d="M27 44a23 27 0 0 1 46 0c0-15-10-22-23-22S27 29 27 44Z" fill={f.hair} />
        </>
      );
    case 2: // topknot
      return (
        <>
          <circle cx="50" cy="16" r="8" fill={f.hair} />
          <path d="M28 43a22 26 0 0 1 44 0c0-14-9-21-22-21S28 29 28 43Z" fill={f.hair} />
        </>
      );
    case 3: // curls
      return (
        <>
          {[
            [32, 32],
            [41, 25],
            [50, 22],
            [59, 25],
            [68, 32],
            [28, 42],
            [72, 42],
          ].map(([cx, cy], i) => (
            <circle key={i} cx={cx} cy={cy} r="9" fill={f.hair} />
          ))}
        </>
      );
    case 4: // side part
      return (
        <path
          d="M27 44c0-16 10-23 23-23 13 0 23 7 23 23 0-9-6-14-13-14-6 0-8 4-16 5-9 1-13 4-17 9Z"
          fill={f.hair}
        />
      );
    default: // bald
      return null;
  }
}

function Eyes({ f }: { f: Features }) {
  const ry = f.eyes === 0 ? 4 : f.eyes === 1 ? 3 : 2;
  return (
    <>
      {[39, 61].map((cx) => (
        <g key={cx}>
          <ellipse cx={cx} cy="48" rx="5" ry={ry} fill="#fff" stroke={INK} strokeWidth="1.4" />
          <circle cx={cx} cy="48" r={Math.min(ry, 2.4)} fill={INK} />
        </g>
      ))}
    </>
  );
}

function Brows({ f }: { f: Features }) {
  const d =
    f.brows === 0
      ? ["M33 40q6-4 12 0", "M55 40q6-4 12 0"] // arched
      : f.brows === 1
        ? ["M33 40h12", "M55 40h12"] // flat
        : ["M33 41q6-5 12-1", "M55 40q6 4 12 1"]; // quizzical
  return (
    <>
      {d.map((path, i) => (
        <path
          key={i}
          d={path}
          stroke={f.hair}
          strokeWidth="2.4"
          fill="none"
          strokeLinecap="round"
        />
      ))}
    </>
  );
}

function Mouth({ f }: { f: Features }) {
  switch (f.mouth) {
    case 0: // smile
      return (
        <path
          d="M42 60q8 7 16 0"
          stroke={INK}
          strokeWidth="2.2"
          fill="none"
          strokeLinecap="round"
        />
      );
    case 1: // neutral
      return (
        <path d="M43 61h14" stroke={INK} strokeWidth="2.2" fill="none" strokeLinecap="round" />
      );
    case 2: // grin
      return (
        <>
          <path d="M41 59q9 9 18 0Z" fill={INK} />
          <path d="M43 60h14" stroke="#fff" strokeWidth="1.6" />
        </>
      );
    default: // smirk
      return (
        <path
          d="M42 61q9 4 15-3"
          stroke={INK}
          strokeWidth="2.2"
          fill="none"
          strokeLinecap="round"
        />
      );
  }
}

function Accessory({ f }: { f: Features }) {
  switch (f.accessory) {
    case 0: // round glasses
      return (
        <g stroke={INK} strokeWidth="1.8" fill="none">
          <circle cx="39" cy="48" r="8" />
          <circle cx="61" cy="48" r="8" />
          <path d="M47 48h6M27 47l4 1M73 47l-4 1" />
        </g>
      );
    case 1: // cap
      return (
        <>
          <path d="M26 38a24 24 0 0 1 48 0Z" fill={f.shirt} stroke={INK} strokeWidth="1.6" />
          <path d="M26 38h30v5H26Z" fill={f.shirt} stroke={INK} strokeWidth="1.6" />
        </>
      );
    case 2: // earrings
      return (
        <>
          <circle cx="27" cy="57" r="2.4" fill="#f2cf6b" stroke={INK} strokeWidth="1" />
          <circle cx="73" cy="57" r="2.4" fill="#f2cf6b" stroke={INK} strokeWidth="1" />
        </>
      );
    default:
      return null;
  }
}

function FacialHair({ f }: { f: Features }) {
  if (f.facialHair === 0) return null;
  if (f.facialHair === 1) {
    return <path d="M43 56q7 4 14 0-7 5-14 0Z" fill={f.hair} />;
  }
  return (
    <path
      d="M31 50c0 14 8 24 19 24s19-10 19-24c-3 10-9 14-19 14s-16-4-19-14Z"
      fill={f.hair}
      opacity="0.9"
    />
  );
}

export function HumanFace({
  seed,
  url,
  className = "",
  title,
}: {
  seed: string;
  url?: string | null;
  className?: string;
  title?: string;
}) {
  const f = useMemo(() => featuresFor(seed), [seed]);

  if (url) {
    return <img src={url} alt={title ?? "a human"} className={`object-cover ${className}`} />;
  }

  return (
    <svg
      viewBox="0 0 100 100"
      className={className}
      role="img"
      aria-label={title ?? "a human to match"}
    >
      <rect width="100" height="100" fill={f.bg} />
      {/* shoulders */}
      <ellipse cx="50" cy="104" rx="36" ry="24" fill={f.shirt} stroke={INK} strokeWidth="1.6" />
      {/* neck */}
      <rect x="44" y="64" width="12" height="16" fill={f.shade} />
      {/* ears */}
      <circle cx="28" cy="50" r="6" fill={f.shade} stroke={INK} strokeWidth="1.4" />
      <circle cx="72" cy="50" r="6" fill={f.shade} stroke={INK} strokeWidth="1.4" />
      {/* head */}
      <ellipse cx="50" cy="47" rx="23" ry="27" fill={f.skin} stroke={INK} strokeWidth="1.8" />
      <FacialHair f={f} />
      <Hair f={f} />
      <Brows f={f} />
      <Eyes f={f} />
      {/* nose */}
      <path d="M50 50v6l3 2" stroke={INK} strokeWidth="1.6" fill="none" strokeLinecap="round" />
      <Mouth f={f} />
      <Accessory f={f} />
    </svg>
  );
}
