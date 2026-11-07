# Rewrite from scratch rather than port Yorick

Yorick already had working React and Vue ports, both passing its full E2E suite against the legacy jQuery Mobile markup, plus a Parse 8 / parse-server 9 upgrade. We chose to start a fresh codebase anyway, because those ports were tied to Parse's object model and a 2015 page structure, and keeping either would have meant keeping both. Yorick is used as a reference for features and behaviour, not as code to carry over: its Playwright specs serve as the feature inventory, and its typed rule modules (`client/src/domain/rules/`) serve as reference tables for checking the new rules.

Horatio launches as a new product with fresh data: nothing is imported from Yorick's MongoDB (decided 2026-10-14). The `legacy_id` columns and the bcrypt password support exist only in case that changes.

## Amendment: one troupe's characters, from Yorick's printout (2026-11-06)

A troupe moving to Horatio asked to bring its characters, rather than have every player rebuild theirs. That is now possible as a one-off, run by the troupe (issue #482): `horatio.import_yorick_print` reads the troupe's **Print Characters** page, saved from Yorick as HTML, and makes each character a sheeted NPC of the troupe, for staff to give to its player as they sign up (#481).

This is not the database import the decision above ruled out, and it doesn't reverse it:

- **It reads a printout, not Yorick's data.** The page is what any troupe's staff can save from Yorick. It carries each sheet as it stands, and the portraits, but no players, XP or history. So there are no accounts or passwords to carry over, and nothing of Parse's object model comes with it.
- **The characters start as NPCs.** Each is checked by Horatio's own rules, with what it breaks flagged, and becomes a player's only when staff give it to them. That step also sets its XP, at the troupe's prices.
- **The troupe reviews the mapping.** Yorick's names are matched to Horatio's through one table, `backend/src/horatio/yorick_names.toml`, with Horatio's spelling fixes (#410). The troupe's lead goes through the dry run's unmatched list and extends the table until it's clean.
- **It records where each came from.** A character keeps its Yorick id in `legacy_id`, so running the import again updates it rather than making it twice.

Since 2026-11-07 (issue #518) the custodian runs it in the app, under **Custodian › Import from Yorick**, rather than as a command on the server: they upload the page, review the dry run, and import it. The mapping table is the same, with each troupe's own names kept in the database over it. A troupe can come across over months, uploading a newer page as players move; a character already in the troupe under a printed name waits for the custodian to choose whether to overwrite it, skip it, or import it beside it. It is still one troupe's printout at a time, not Yorick's data.

If a troupe can get a database export from Yorick (its Parse/Mongo data), that would carry players' emails and XP history as well. The parser would then read that instead; the mapping table would carry over.

## Considered Options

- **Ship the Vue port and modernise behind it.** Least work to a new UI, but leaves Parse, MongoDB and per-object ACLs in place.
- **Keep Parse, replace the front end only.** Same problem; the data model and permission model were the parts most in need of change.

## Not carried over

Referendums, patronage (PayPal payments) and character relationships are deliberately left out of Horatio. Everything else in Yorick is in scope: characters and their sheets, XP history, approvals, troupes, long texts, trait descriptions, portraits and the printable sheet.
