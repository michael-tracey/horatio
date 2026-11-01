/**
 * A delivered downtime result, read back into its parts so the Results tab can show
 * each response under the action it answers. Horatio writes the message
 * (horatio.responses.compose): a heading, then for each answered question a block
 * "**question**", "*Your action:* …", "*Result:* …", and for feeding "**Feeding**",
 * "*Your feeding:* …" and the answer. The message is what was delivered, kept as it
 * was, so it is read rather than rebuilt from today's responses.
 */

export type ResultPart = {
  /** The question, or "Feeding". */
  heading: string;
  /** What the player wrote, or their feeding; "" when the message has none. */
  action: string;
  actionLabel: "Your action" | "Your feeding";
  result: string;
};

const HEADING = /^\*\*(Updated d|D)owntime results for .*\*\*$/;
const BOLD = /^\*\*(.+)\*\*$/;
const ACTION = /^\*Your (action|feeding):\* ?(.*)$/;
const RESULT = /^\*Result:\* ?(.*)$/;

/** The message's parts, or null for a message not in Horatio's own shape (one
 * written some other way), which is then shown as it is. */
export function resultParts(message: string): ResultPart[] | null {
  const lines = message.split("\n");
  if (!HEADING.test(lines[0] ?? "")) return null;
  const parts: ResultPart[] = [];
  let part: ResultPart | null = null;
  let field: "heading" | "action" | "result" = "heading";
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i]!;
    const bold = line.match(BOLD);
    // A new block starts after a blank line, with its action next (or, for feeding, perhaps none).
    if (bold && lines[i - 1] === "" && (ACTION.test(lines[i + 1] ?? "") || bold[1] === "Feeding")) {
      part = { heading: bold[1]!, action: "", actionLabel: "Your action", result: "" };
      parts.push(part);
      field = "heading";
      continue;
    }
    if (part === null) {
      if (line === "") continue;
      return null;
    }
    const action = field === "heading" ? line.match(ACTION) : null;
    const result = field !== "result" ? line.match(RESULT) : null;
    if (action) {
      part.action = action[2]!;
      part.actionLabel = action[1] === "feeding" ? "Your feeding" : "Your action";
      field = "action";
    } else if (result) {
      part.result = result[1]!;
      field = "result";
    } else if (field === "heading" || (field === "action" && part.actionLabel === "Your feeding")) {
      // Feeding's answer follows its one-line summary, unlabelled.
      part.result = line;
      field = "result";
    } else {
      part[field] += `\n${line}`;
    }
  }
  if (!parts.length) return null;
  return parts.map((p) => ({ ...p, action: p.action.trim(), result: p.result.trim() }));
}
