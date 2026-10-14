# Rules are data: generic rule sets with per-troupe house rules

Each splat has a generic rule set that ships with the system, covering trait costs and downtime allowance rules. Any troupe can house-rule any value in it. Rules are therefore stored as data rather than written into code, because troupes routinely play by home rules and expecting a code change for each one would not work. A character always plays by its home troupe's rules (the plain rule set if it has none), even when it belongs to several troupes. Every purchase records the cost actually paid, so changing a house rule never rewrites a character's past XP. The one exception is reconciliation: when a character joins a home troupe, its purchases are compared with that troupe's rules and the differences are settled by the troupe's staff. Characters are built outside any troupe under the plain rule set, so every character goes through reconciliation when it first gets a home troupe.

## Considered Options

- **Rules in code, one module per splat (Yorick's approach).** Simple and easy to test, but any house rule needs a developer.
- **The rules of whichever troupe the character is acting in.** Rejected because a character in two troupes would have two different XP totals for the same sheet.
- **Recalculate past purchases when a rule changes.** Rejected because it silently changes approved characters' histories.

## Consequences

- Rule-set updates from the system must merge with troupes' house rules rather than replace them.
- Rule changes take effect for new purchases only, so a troupe can see what a change will affect before saving it.
