/** How ready one submitted downtime is to deliver, as the Delivery tab is told. */
export type Readiness = {
  character_name: string;
  answered: number;
  to_answer: number;
  delivered: boolean;
  changed: boolean;
  due: boolean;
};

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/**
 * What delivering would do: the downtimes with every response written and
 * something new for the player go by default; those partly written only if asked.
 */
export function deliveryPlan<T extends Readiness>(participants: T[]) {
  const finished = (p: T) => p.answered === p.to_answer;
  return {
    finished: participants.filter(finished).length,
    ready: participants.filter((p) => p.due && finished(p)),
    partial: participants.filter((p) => p.due && !finished(p)),
    current: participants.filter((p) => p.delivered && !p.due),
    unwritten: participants.filter((p) => !p.delivered && !p.due),
  };
}

/** "Delivered 3 downtimes, 1 of them an update." */
export function deliveredText(delivered: number, updated: number): string {
  if (delivered === 0) return "Nothing new to deliver.";
  const what = `Delivered ${plural(delivered, "downtime", "downtimes")}`;
  if (updated === 0) return `${what}.`;
  if (updated === delivered) return `${what}, as ${delivered === 1 ? "an update" : "updates"}.`;
  return `${what}, ${updated} of them ${updated === 1 ? "an update" : "updates"}.`;
}

/** The facts to weigh before closing submissions. */
export function closeFacts({
  participants,
  submitted,
  due,
  lateUntil,
  isPast,
}: {
  participants: number;
  submitted: number;
  due: string;
  lateUntil: string | null;
  isPast: boolean;
}): string[] {
  const missing = participants - submitted;
  return [
    isPast ? `It was due ${due}.` : `It isn't due until ${due}.`,
    missing === 0
      ? participants === 1
        ? "The 1 participant has submitted."
        : `All ${participants} participants have submitted.`
      : `${missing} of ${plural(participants, "participant", "participants")} ${missing === 1 ? "hasn't" : "haven't"} submitted.`,
    ...(missing > 0 && lateUntil ? [`Late downtimes are taken until ${lateUntil}.`] : []),
    "Once closed, nobody can submit, and the cycle can't be opened again.",
  ];
}

/** The facts to weigh before marking a cycle complete. */
export function completeFacts({ unwritten, responses, undelivered }: { unwritten: number; responses: number; undelivered: number }): string[] {
  return [
    unwritten === 0 ? "Every response is written." : `${unwritten} of ${plural(responses, "response", "responses")} ${unwritten === 1 ? "isn't" : "aren't"} written.`,
    undelivered === 0
      ? "Players have every result as it stands."
      : `${plural(undelivered, "downtime has", "downtimes have")} results not yet delivered.`,
    "Once complete, responses and feeding answers can't be written or changed.",
  ];
}
