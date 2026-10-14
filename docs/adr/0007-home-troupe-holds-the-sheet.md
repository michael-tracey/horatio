# The home troupe holds the sheet

**Supersedes [ADR 0006](0006-troupe-standing-and-per-troupe-approval.md).**

A character has one home troupe, and that troupe alone holds its sheet. Asking a troupe to be home, and its storytellers or assistant storytellers accepting (with reconciliation), is the only acceptance; there are no per-troupe drafts, approved sheets or sheet-change requests. Other troupes the character is in are visits: their staff can see the sheet but approve nothing and award no experience. Edits take effect at once, whether or not the character is in a troupe. The one exception is disciplines: once the character has a home troupe, each discipline dot it buys waits on that troupe, with the experience spent at once and refunded if the troupe declines.

We moved away from every troupe approving its own copy (ADR 0006) because it left characters stuck as drafts nobody had been asked to approve, locked sheets while requests waited on several troupes, and made the simple case (one character, one troupe) feel like paperwork. Disciplines are kept under approval because learning one needs a teacher and a downtime, which is the home troupe's call.

## Consequences

- Only a waiting home troupe request locks the sheet, so the differences it settles stay the differences there are. A waiting discipline blocks moving home troupes and further changes to that discipline.
- The sheet as accepted is the floor: the player can undo purchases since, but not lower accepted dots or approved discipline dots.
- Downtimes take every active PC whose home troupe runs the cycle, and work out allowances from the sheet as it stands, leaving out discipline dots still waiting.
- Only the home troupe awards experience; all of it, including any carried over from an earlier home troupe, can be spent.
- Printing shows the sheet as it stands, with waiting discipline dots marked.
- `troupe_memberships.standing` is gone. Old `sheet_change` approvals are kept for history; any still waiting were withdrawn.
