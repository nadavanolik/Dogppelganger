// Rebuilds the image manifests from whatever files live in public/dogs/ and public/humans/.
// Run after adding or removing photos:  npm run images
import { readdirSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const exts = /\.(jpe?g|png|webp|avif|gif)$/i;

const sets = [
  { dir: join(root, "public", "dogs"), out: join(root, "src", "lib", "dogImages.json") },
  { dir: join(root, "public", "humans"), out: join(root, "src", "lib", "humanImages.json") },
];

for (const { dir, out } of sets) {
  const files = readdirSync(dir)
    .filter((f) => exts.test(f))
    .sort();
  writeFileSync(out, JSON.stringify(files, null, 4) + "\n");
  console.log(`${out.split("/").pop()} <- ${files.length} file(s) from ${dir.split("/").slice(-2).join("/")}/`);
}
