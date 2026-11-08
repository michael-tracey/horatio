# Put the Dark Pack resources here

Horatio can show Paradox's **Dark Pack logo** on its About page, and the **clan
symbols** on game badges, under the
[Dark Pack Agreement](https://www.paradoxinteractive.com/games/world-of-darkness/community/dark-pack-agreement).
They aren't part of Horatio and must never be committed. Everything in this folder
except this README is ignored by git and kept out of the image, because the
agreement's licence is personal and can't be passed on under Horatio's AGPL.
Each server's operator fetches the kit and imports it themselves.

## On a server

Use **Custodian › Tools › Dark Pack resources**: tick the agreement and choose
**Fetch and import**. The server downloads Paradox's kit from the agreement's
download (a shared Dropbox folder, about 450 MB), imports it into the folder
`HORATIO_DARK_PACK_DIR` names, and deletes the download. Deploys don't copy this
folder any more; the server keeps its own on permanent storage
(`deploy/README.md`).

If the fetch fails, import the kit on your own computer as below, zip the folder
it wrote, and upload the zip in the same tool.

**Custodian › Tools › VTES symbols** fetches the symbols of *Vampire: The Eternal
Struggle* from [KRCG](https://static.krcg.org/) into `vtes/` here, for later use.
Wherever Horatio shows them, it credits KRCG and gives Paradox's notice.

## On your own computer

`./start-local.sh` uses this folder, so the Tools tab works locally too. Or import
with the command:

1. Download the free assets from the agreement's page ("Download Free Content").
   That's one zip holding two: **World of Darkness Community Assets**, which
   Horatio uses, and **WoD-Logos-and-Symbols**, which it reads for the clans the
   newer kit lacks (Giovanni, Cappadocians, Lamia, Nagaraja).
2. Import them, from `backend/`:

   ```bash
   uv run python -m horatio.dark_pack "path/to/WoD Community Assets.zip"
   ```

   The download as it comes works, as do the two zips inside it, named one after
   the other. This reads the zips in place and writes only what Horatio uses into
   this folder: the Dark Pack logo, each clan's symbol (black and white) at the
   sizes Horatio serves, and `manifest.json`. That's about a megabyte, not the
   zips' 450.
3. Horatio picks them up at once; no restart needed.

Without these files Horatio works as before. The About page still gives the
agreement's notices; it just has no logo, and badges show only the logos the
custodian uploads. An uploaded clan logo always wins over the Dark Pack symbol.
