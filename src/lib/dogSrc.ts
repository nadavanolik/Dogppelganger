import dogSlugs from "./dogImages.json";

const SLUGS = dogSlugs as string[];

export const DOG_COUNT = SLUGS.length;

/** The three derivatives the ingest writes — see backend/app/storage/layout.py. */
export type DogSize = "128" | "256" | "512";

// 512 is the archival JPEG (AFHQ's native size); the smaller two are WebP,
// which is ~30% lighter at the same quality.
const EXT: Record<DogSize, string> = { "128": "webp", "256": "webp", "512": "jpg" };

/**
 * Turn a dog index from the API into an image URL.
 *
 * The backend names a dog by its position in `dogImages.json` rather than
 * sending a filename or the bytes, so the 5,239 photos stay a purely frontend
 * concern — nginx serves them straight off the `dogdata` volume with a
 * year-long immutable cache. Out-of-range indices wrap instead of 404ing, so
 * the two sides can't get fatally out of step.
 *
 * Default to "256": the display size. Use "128" for game tiles and grids,
 * "512" only where the photo is the focus of the page.
 */
export function dogSrc(index: number, size: DogSize = "256"): string {
  const i = ((index % SLUGS.length) + SLUGS.length) % SLUGS.length;
  return dogSrcBySlug(SLUGS[i], size);
}

/** Same, for endpoints that name a dog by its stable slug rather than an index. */
export function dogSrcBySlug(slug: string, size: DogSize = "256"): string {
  return `/dogs/${size}/${slug}.${EXT[size]}`;
}
