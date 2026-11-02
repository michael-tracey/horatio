/**
 * How the rule set writes a check's strength: one setting, or one while the
 * character is built and another once creation is finished (a sect's merits:
 * needed to finish, then for review). `label` names a single setting.
 */
export function writtenStrength(
  rule: { strength: string; once_finished?: string | null },
  label: (strength: string) => string,
): string {
  const first = label(rule.strength);
  if (!rule.once_finished) return first;
  return `${first}, then ${label(rule.once_finished).toLowerCase()}`;
}
