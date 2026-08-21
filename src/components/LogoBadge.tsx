// The app's logo: the dog on a coral disc inside the ink ring.
//
// public/favicon.svg and the icons under public/ draw this same mark — if the
// styling here changes, re-run backend/scripts/make_brand_assets.py so the tab
// icon does not drift from the header.
export function LogoBadge({ className = "" }: { className?: string }) {
  return (
    <div
      className={`h-10 w-10 rounded-full bg-primary border-2 border-[var(--ink)] flex items-center justify-center text-xl shadow-pop-sm ${className}`}
    >
      🐶
    </div>
  );
}
