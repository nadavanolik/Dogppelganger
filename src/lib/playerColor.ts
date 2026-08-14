/**
 * A stable colour per player, so a claim is attributable at a glance.
 *
 * The same player is the same colour on the board, in the scoreboard and on the
 * reveal — which is what lets you watch someone commit to a pairing and react to
 * it. Derived from the id rather than assigned by join order, so it survives a
 * reconnect and agrees across everyone's screen without the server sending it.
 */

// Spaced around the wheel and kept off the yellows that vanish on the cream
// background. Twelve of them, matching MAX_PLAYERS.
const HUES = [352, 18, 40, 96, 140, 166, 190, 212, 238, 268, 292, 320];

function hash(value: string): number {
  let h = 2166136261;
  for (let i = 0; i < value.length; i++) {
    h ^= value.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** A saturated fill that reads against the ink border in both themes. */
export function playerColor(playerId: string): string {
  return `hsl(${HUES[hash(playerId) % HUES.length]} 72% 52%)`;
}

/** The same colour, faded — for other people's lines during the reveal. */
export function playerColorSoft(playerId: string): string {
  return `hsl(${HUES[hash(playerId) % HUES.length]} 60% 72%)`;
}
