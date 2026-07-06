# Nav flatten + dedupe

## 1. Nav changes (`src/components/AppShell.tsx`)

New top bar for signed-in users:

```
[logo]  🐕 Match   🎮 Play   🖼 Gallery   💬 Forum       [💌] [🔔] [avatar ▾]
```

- **Play** — plain `NavLink` to `/play` (the hub with Solo / Multiplayer cards). No dropdown, no ▾. Label becomes `🎮 Play`.
- **Gallery** and **Forum** — promoted to top-level `NavLink`s. The Community dropdown is deleted entirely.
- Match keeps its label style; add the 🐕 emoji so all four items feel consistent.
- Mobile hamburger sheet mirrors the same four items (plus Messages, Profile) — already covered.

## 2. Avatar dropdown cleanup

Remove Messages and Notifications from the avatar menu — they're always one click away in the header (💌 and 🔔). Duplication just adds noise.

New dropdown contents:
- `@username` label
- My profile & dogs → `/profile`
- Log out

(Settings stub not added — no functionality behind it, will introduce later if needed.)

## 3. Home vs Profile split — clear roles

Today both surfaces show stats + queue + my-dogs. Fix by giving each a distinct job:

**Signed-in home (`/`)** — "what's happening right now"
- Greeting header + `＋ New match` CTA (keep)
- Mini activity stats: In queue · Unread alerts · New DMs · Likes received (keep)
- Live queue panel — only when items are cooking (keep)
- Forum · latest + Gallery · fresh two-column (keep)
- Jump into Play card (keep)
- **Remove** the "Your dogs" mini-strip — that belongs on Profile.

**Profile (`/profile`)** — "who I am + my collection"
- Identity header (avatar, @username, email) — keep
- Totals only: Total dogs · Shared · Forum posts · Reactions received (keep — these are lifetime totals, not "activity")
- **Remove** the live queue section (queue is transient, lives on home)
- My dogs grid with share/discard controls — keep as the main body
- Add small tabs above the grid: **All · Shared · Private** — lets user filter their own collection, gives Profile a job Home doesn't have.

Result: Home = ephemeral / actionable / community entry. Profile = durable / identity / dog collection management. Stats appear in both but framed differently (mini "right now" counts vs lifetime totals).

## Files touched

- `src/components/AppShell.tsx` — remove Community + Play dropdowns, add Gallery/Forum/Play as flat NavLinks, prune avatar menu.
- `src/routes/index.tsx` — drop the "Your dogs" section from `SignedInHome`.
- `src/routes/profile.tsx` — remove the queue section; add All/Shared/Private filter tabs above the grid.

No other routes, store logic, or styling changes.
