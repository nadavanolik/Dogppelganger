import dogImages from "./dogImages.json";
import { dogSrc } from "./dogSrc";

export const BREEDS = [
  {
    name: "Golden Retriever",
    emoji: "🐕",
    bg: "from-amber-200 to-orange-300",
    trait: "sunny optimist",
  },
  {
    name: "Corgi",
    emoji: "🐶",
    bg: "from-orange-200 to-rose-300",
    trait: "short kingdom, big attitude",
  },
  { name: "Shiba Inu", emoji: "🦊", bg: "from-yellow-200 to-amber-400", trait: "polite chaos" },
  {
    name: "French Bulldog",
    emoji: "🐺",
    bg: "from-stone-200 to-stone-400",
    trait: "professional loafer",
  },
  {
    name: "Border Collie",
    emoji: "🐕‍🦺",
    bg: "from-slate-200 to-slate-400",
    trait: "over-caffeinated genius",
  },
  { name: "Dachshund", emoji: "🌭", bg: "from-red-200 to-amber-300", trait: "long. very long." },
  { name: "Poodle", emoji: "🐩", bg: "from-pink-200 to-fuchsia-300", trait: "runway attendee" },
  { name: "Husky", emoji: "🐺", bg: "from-sky-100 to-cyan-300", trait: "screams for no reason" },
  { name: "Pug", emoji: "🐽", bg: "from-yellow-100 to-amber-200", trait: "snores heroically" },
  { name: "Beagle", emoji: "🐕", bg: "from-lime-100 to-emerald-200", trait: "nose-first life" },
  {
    name: "Chihuahua",
    emoji: "🐭",
    bg: "from-fuchsia-100 to-pink-200",
    trait: "tiny, furious, iconic",
  },
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
  // dogImages.json holds slugs, not filenames — dogSrc turns one into a URL
  // for the right derivative. See src/lib/dogSrc.ts.
  const image = dogImages.length > 0 ? dogSrc(h) : undefined;
  return { ...base, image };
}

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
