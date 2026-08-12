import dogImages from "./dogImages.json";

const FILES = dogImages as string[];

export const DOG_COUNT = FILES.length;

/**
 * Turn a dog index from the API into an image URL.
 *
 * The backend names a dog by its position in this list rather than sending a
 * filename or the bytes, so the 5,239 photos in `public/dogs` stay a purely
 * frontend concern (nginx already serves them). Out-of-range indices wrap
 * instead of 404ing, so the two sides can't get fatally out of step.
 */
export function dogSrc(index: number): string {
  const i = ((index % FILES.length) + FILES.length) % FILES.length;
  return `/dogs/${FILES[i]}`;
}
