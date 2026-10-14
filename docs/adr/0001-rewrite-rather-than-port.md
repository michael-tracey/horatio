# Rewrite from scratch rather than port Yorick

Yorick already had working React and Vue ports, both passing its full E2E suite against the legacy jQuery Mobile markup, plus a Parse 8 / parse-server 9 upgrade. We chose to start a fresh codebase anyway, because those ports were tied to Parse's object model and a 2015 page structure, and keeping either would have meant keeping both. Yorick is used as a reference for features and behaviour, not as code to carry over: its Playwright specs serve as the feature inventory, its typed rule modules (`client/src/domain/rules/`) serve as reference tables for checking the new rules, and its data is imported once from MongoDB.

## Considered Options

- **Ship the Vue port and modernise behind it.** Least work to a new UI, but leaves Parse, MongoDB and per-object ACLs in place.
- **Keep Parse, replace the front end only.** Same problem; the data model and permission model were the parts most in need of change.
