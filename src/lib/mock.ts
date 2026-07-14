import dogImages from "./dogImages.json";
import humanImages from "./humanImages.json";

export const BREEDS = [
  { name: "Golden Retriever", emoji: "🐕", bg: "from-amber-200 to-orange-300", trait: "sunny optimist" },
  { name: "Corgi", emoji: "🐶", bg: "from-orange-200 to-rose-300", trait: "short kingdom, big attitude" },
  { name: "Shiba Inu", emoji: "🦊", bg: "from-yellow-200 to-amber-400", trait: "polite chaos" },
  { name: "French Bulldog", emoji: "🐺", bg: "from-stone-200 to-stone-400", trait: "professional loafer" },
  { name: "Border Collie", emoji: "🐕‍🦺", bg: "from-slate-200 to-slate-400", trait: "over-caffeinated genius" },
  { name: "Dachshund", emoji: "🌭", bg: "from-red-200 to-amber-300", trait: "long. very long." },
  { name: "Poodle", emoji: "🐩", bg: "from-pink-200 to-fuchsia-300", trait: "runway attendee" },
  { name: "Husky", emoji: "🐺", bg: "from-sky-100 to-cyan-300", trait: "screams for no reason" },
  { name: "Pug", emoji: "🐽", bg: "from-yellow-100 to-amber-200", trait: "snores heroically" },
  { name: "Beagle", emoji: "🐕", bg: "from-lime-100 to-emerald-200", trait: "nose-first life" },
  { name: "Chihuahua", emoji: "🐭", bg: "from-fuchsia-100 to-pink-200", trait: "tiny, furious, iconic" },
  { name: "Great Dane", emoji: "🐴", bg: "from-indigo-100 to-blue-300", trait: "horse in denial" },
];

export type Breed = (typeof BREEDS)[number] & { image?: string };

export function randomBreed(seed?: string): Breed {
  let h = 0;
  if (seed) {
    for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  } else {
    h = Math.floor(Math.random() * 1000000);
  }
  const base = BREEDS[h % BREEDS.length];
  const image = dogImages.length > 0 ? `/dogs/${dogImages[h % dogImages.length]}` : undefined;
  return { ...base, image };
}

// Deterministic real-photo path for a given index; undefined when no files are in public/dogs/
// (so callers fall back to the breed emoji). Run `npm run dogs` after adding photos.
export function dogImageAt(i: number): string | undefined {
  return dogImages.length > 0 ? `/dogs/${dogImages[Math.abs(i) % dogImages.length]}` : undefined;
}

// Deterministic real human-photo path for a given index; undefined when no files are in
// public/humans/ (so callers fall back to an emoji). Run `npm run images` after adding photos.
export function humanImageAt(i: number): string | undefined {
  return humanImages.length > 0 ? `/humans/${humanImages[Math.abs(i) % humanImages.length]}` : undefined;
}

// True when a humanImg/avatar value is a real image reference (uploaded data URL, remote URL, or
// a file served from public/) rather than an emoji. The single source of truth for the img-vs-emoji
// decision across DogCard, HumanAvatar, game, lobbies and home.
export function isPhoto(src: string): boolean {
  return src.startsWith("data:") || src.startsWith("http") || src.startsWith("/");
}

// First integer found in a filename, e.g. "human2.png" -> 2, "dog1 2.jpg" -> 1. null if none.
function fileNumber(name: string): number | null {
  const m = name.match(/(\d+)/);
  return m ? parseInt(m[1], 10) : null;
}

// A human photo and a dog photo that share the same number (human2.png ↔ dog2.png), so a match can
// show the same person with their assigned dog. Built from the public/humans and public/dogs folders.
export type PhotoPair = { n: number; human: string; dog: string };

// Every dog image path that actually exists in public/dogs (per the generated manifest).
const DOG_IMAGE_SET = new Set(dogImages.map((d) => `/dogs/${d}`));

// True when a match's dog picture is a real file in public/dogs. Undefined breedImage counts as ok
// (that match falls back to a breed emoji, so there is no broken photo). Used to prune the gallery
// of cards whose dog file has been deleted or renamed.
export function isKnownDogImage(breedImage?: string): boolean {
  return !breedImage || DOG_IMAGE_SET.has(breedImage);
}

// The single dog every freshly uploaded human is matched to. Change UPLOAD_DOG_FILE to point new
// uploads at a different photo; falls back to any dog numbered 3, then undefined (breed emoji).
const UPLOAD_DOG_FILE = "dog3.jpeg";
export const UPLOAD_DOG_SRC: string | undefined = dogImages.includes(UPLOAD_DOG_FILE)
  ? `/dogs/${UPLOAD_DOG_FILE}`
  : (() => {
      const byNum = dogImages.find((d) => fileNumber(d) === 3);
      return byNum ? `/dogs/${byNum}` : undefined;
    })();

export const PHOTO_PAIRS: PhotoPair[] = (() => {
  const dogsByNum = new Map<number, string>();
  for (const d of dogImages) {
    const n = fileNumber(d);
    if (n != null && !dogsByNum.has(n)) dogsByNum.set(n, `/dogs/${d}`);
  }
  const pairs: PhotoPair[] = [];
  for (const h of humanImages) {
    const n = fileNumber(h);
    if (n != null && dogsByNum.has(n)) {
      pairs.push({ n, human: `/humans/${h}`, dog: dogsByNum.get(n)! });
    }
  }
  return pairs.sort((a, b) => a.n - b.n);
})();

export const SAMPLE_HUMANS = ["😀", "🧑", "👩", "🧔", "👨‍🦰", "👩‍🦱", "🧑‍🎤", "👵", "🧑‍🚀", "👩‍🌾"];

export const SAMPLE_POSTS = [
  {
    title: "I got matched with a Shiba Inu and my life makes sense now",
    body: "For 32 years I thought I was a Golden. Turns out I've been misreading myself. The polite chaos hits.",
    author: "moodyoak",
  },
  {
    title: "Best strategy for the multiplayer match game?",
    body: "I keep losing to my roommate. Any tips beyond 'squint at the ears'?",
    author: "corgi_core",
  },
  {
    title: "Petition to add Alaskan Klee Kai",
    body: "The tiny husky lobby demands representation.",
    author: "hufflepupp",
  },
];
