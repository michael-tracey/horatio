# Put the Dark Pack resources here

Horatio can show Paradox's **Dark Pack logo** on its About page, and the **clan
symbols** on game badges, under the
[Dark Pack Agreement](https://www.paradoxinteractive.com/games/world-of-darkness/community/dark-pack-agreement).
They aren't part of Horatio and must never be committed. Everything in this folder
except this README is ignored by git and kept out of the image, because the
agreement's licence is personal and can't be passed on under Horatio's AGPL.
Each server's operator fetches the kit and imports it themselves.

1. Download the free assets from the agreement's page ("Download Free Content").
   Horatio uses the **World of Darkness Community Assets** zip, and also reads
   **WoD-Logos-and-Symbols** for the clans the newer kit lacks (Giovanni,
   Cappadocians, Lamia, Nagaraja).
2. Import them, from `backend/`:

   ```bash
   uv run python -m horatio.dark_pack \
     "path/to/World of Darkness Community Assets.zip" \
     path/to/WoD-Logos-and-Symbols.zip
   ```

   This reads the zips in place and writes only what Horatio uses into this
   folder: the Dark Pack logo, each clan's symbol (black and white) at the sizes
   Horatio serves, and `manifest.json`. That's about a megabyte, not the zips'
   450.
3. Restart Horatio: `./start-local.sh` uses this folder, and `deploy/deploy.sh`
   copies it to the server, where `HORATIO_DARK_PACK_DIR` names it.

Without these files Horatio works as before. The About page still gives the
agreement's notices; it just has no logo, and badges show only the logos the
custodian uploads. An uploaded clan logo always wins over the Dark Pack symbol.
