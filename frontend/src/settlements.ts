/** How reconciliation differences and their settlements read, for players and staff alike. */

type DifferenceLike = {
  difference: string;
  rating: number;
  old_cost: number;
  new_cost: number | null;
  // A difference about extra creation picks has no trait.
  extra?: boolean;
};

export function settlementLabel(settlement: string, d: DifferenceLike): string {
  switch (settlement) {
    case "pay_difference":
      return "Pay the difference";
    case "refund_difference":
      return "Refund the difference";
    case "remove_and_refund":
      return "Remove it and refund the XP";
    case "pay_for_dots":
      return `Pay ${d.new_cost} XP to keep these dots`;
    case "remove_dots":
      return "Remove the trait";
    case "add_free_dots":
      return "Take them (place them in character creation)";
    case "keep_price":
      if (d.difference === "creation_differs") return d.extra ? "Don't take them" : "Keep the free dots";
      return d.difference === "not_allowed" ? "Keep it at the price paid" : "Keep the price paid";
    default:
      return settlement;
  }
}

export function describeDifference(d: DifferenceLike, where = "there"): string {
  if (d.difference === "not_allowed") return `paid ${d.old_cost}, not allowed ${where}`;
  if (d.difference === "cost_differs") return `paid ${d.old_cost}, costs ${d.new_cost} ${where}`;
  if (d.extra) return `this troupe gives more starting dots`;
  return `${d.rating} free dots from creation, which this troupe does not give`;
}
