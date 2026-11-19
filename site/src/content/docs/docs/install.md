---
title: Install
description: What boilerRomM needs, and how to put it on your Steam Deck or other SteamOS device while there is no release.
---

## What you need

- A Steam Deck, or another x86-64 device running SteamOS or Bazzite in Game Mode
- [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) on that device
- A [RomM](https://romm.app) server, version **5.4.1 or newer**, that the device can reach
- About 800 MB of free space for the emulators, plus room for the games you download
- A free [SteamGridDB](https://www.steamgriddb.com) account for artwork (setup signs you in through Steam)

boilerRomM brings no games, BIOS, firmware or keys. It works with the RomM server you run and the files you have
put on it.

## Install from source

There is no release yet, so for now you build boilerRomM and deploy it from a computer with
[Decky Toolkit](https://jackhric.github.io/decky-toolkit/). You need Node.js with pnpm, and
[uv](https://docs.astral.sh/uv/) for the Python side.

1. Pair Decky Toolkit with your device. Its [quick start](https://jackhric.github.io/decky-toolkit/docs/getting-started/)
   covers installing its plugin and pairing.
2. Get the source and build it:

   ```sh
   git clone https://github.com/jackhric/boilerRomM.git
   cd boilerRomM
   pnpm install
   uv pip install --target py_modules --no-deps yt-dlp   # plays trailers; not kept in git
   pnpm build
   ```

3. Deploy it to the paired device:

   ```sh
   npx decky-toolkit dev
   ```

4. On the device, open Quick Access (…) → **boilerRomM** → **Set up boilerRomM** and follow
   [first-run setup](../setup/).

## Install from a release

When the first release is out, it will install like other Decky plugins that are not in the store yet: turn on
Decky's **Developer mode**, open **Developer → Install Plugin from URL**, and enter the address this page will give.
Watch [Releases on GitHub](https://github.com/jackhric/boilerRomM/releases) to hear about it.

## Remove it

To free the space first, remove games from **Settings > Storage** in boilerRomM, or with **Remove from this device**
in a game's menu. **Settings > About → Wipe and restart** removes sign-ins, emulators and settings but keeps downloaded
games and saves. Then uninstall boilerRomM from Decky's plugin list.
