# Downtimes run inside Horatio, replacing Google Forms and Sheets

The troupe ran downtimes with a Google Form feeding a Google Sheet, driven by Apps Script (`lotslarp-st-automation-ms`). Horatio takes that over entirely: forms, submissions, assignment, responses and delivery are records in Horatio, and storytellers can add custom questions to each cycle's form. Most of the old tool's complexity came from working around a spreadsheet: colour-coded assignment, paired submission and response rows, name matching and re-importing form responses. Those workarounds are not carried over. What the old tool does that is about downtimes is carried over: random fill tables, influence-driven rumours, progress views, delivery to Discord and email, test mode, and previewing before sending.

## Consequences

- Downtime cycles belong to a troupe, and each character takes part only through its home troupe.
- Action allowances are computed from the character's approved sheet when the cycle opens, rather than being whatever the form happened to ask that month.
- When a cycle opens, the form's questions are copied into it, so editing a later form never changes the wording an old submission answered.
