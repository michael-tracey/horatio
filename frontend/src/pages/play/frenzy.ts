import type { PlayReference } from "../../api/types";

const signed = (label: string, value: number) => (value < 0 ? `− ${label} ${-value}` : `+ ${label} ${value}`);

/**
 * Resisting frenzy with the character's own numbers (MET: VtM core p. 302; issue
 * #371): Mental + Willpower now, with what merits add, against 10 + Beast traits,
 * counting the ones a merit or flaw adds or takes away, and 5 more at Humanity 2 or
 * less (p. 303). "You: 9 against 12", with the working of each side.
 */
export function frenzyNumbers(
  resist: PlayReference["frenzy"],
  willpower: number,
  beast: number,
  morality: { name: string; value: number } | null,
  on: readonly string[] = [],
): { pool: number; against: number; poolParts: string; againstParts: string } {
  const [mental, ...more] = resist.parts;
  const pool = resist.parts.reduce((sum, p) => sum + p.value, 0) + willpower;
  // Those that hold while a switch is on: Heart of Darkness's removed heart (#822). A view kept on the phone from before has none.
  const switched = (resist.switched_beast ?? []).filter((p) => on.includes(p.switch));
  const beastParts = [...resist.beast, ...switched];
  const counted = Math.max(0, beast + beastParts.reduce((sum, p) => sum + p.value, 0));
  const low = morality?.name === "Humanity" && morality.value <= 2 ? 5 : 0;
  const poolParts = [`${mental?.label ?? "Mental"} ${mental?.value ?? 0}`, ...more.map((p) => signed(p.label, p.value)), `+ Willpower ${willpower}`].join(" ");
  const againstParts = ["10", `+ Beast traits ${beast}`, ...beastParts.map((p) => signed(p.label, p.value)), ...(low ? ["+ 5 (Humanity 2 or less)"] : [])].join(" ");
  return { pool, against: 10 + counted + low, poolParts, againstParts };
}
