import type { GameRsvpsOut, RsvpOut } from "../../api/types";

export type Answer = NonNullable<GameRsvpsOut["my_answer"]>;

/** The three answers, in the order they are offered, each with its label. */
export const ANSWERS: { answer: Answer; label: string }[] = [
  { answer: "coming", label: "Coming" },
  { answer: "maybe", label: "Maybe" },
  { answer: "not_coming", label: "Not coming" },
];

export function answerLabel(answer: Answer): string {
  return ANSWERS.find((a) => a.answer === answer)!.label;
}

/** How many said each, leaving out answers nobody gave: "3 coming · 1 maybe", or "No answers yet". */
export function countsText(game: Pick<GameRsvpsOut, "coming" | "maybe" | "not_coming">): string {
  const parts = [
    game.coming && `${game.coming} coming`,
    game.maybe && `${game.maybe} maybe`,
    game.not_coming && `${game.not_coming} not coming`,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "No answers yet";
}

/** Staff's list of who said what, grouped by answer in the order offered, leaving out empty groups. */
export function byAnswer(answers: RsvpOut[]): { answer: Answer; label: string; people: RsvpOut[] }[] {
  return ANSWERS.map(({ answer, label }) => ({ answer, label, people: answers.filter((a) => a.answer === answer) })).filter((g) => g.people.length > 0);
}

/** A calendar link as a calendar app on a phone or computer opens it to subscribe: webcal:// in place of https://. */
export function webcal(url: string): string {
  return url.replace(/^https?:\/\//, "webcal://");
}

/** What the toast says after answering: "Coming: Sat 12 Jan, 7 pm GMT", or "Answer taken back". */
export function answeredText(answer: Answer | null, when: string): string {
  if (answer === null) return "Answer taken back";
  return `${answerLabel(answer)}: ${when}`;
}
