/**
 * An XP total on the sheet, with a true minus sign: Spent is net of refunds and
 * flaws taken, so it can be below 0 (#548).
 */
export function xpTotal(amount: number): string {
  return amount < 0 ? `−${-amount}` : `${amount}`;
}
