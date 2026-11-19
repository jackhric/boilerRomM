# boilerRomM

A Decky Loader plugin that brings games from a [RomM](https://romm.app) server to a Steam device.

Browse your RomM library in a storefront inside Steam's Big Picture UI and download a game into RetroDECK's ROM
folder. An installed game is a Steam library entry: it launches through RetroDECK, shows in Settings > Storage,
has Uninstall in its menu, and appears on Steam's Downloads page while it downloads. RomM stays the catalogue.

## Setup

1. Open the Quick Access panel, enter the RomM address and press **Connect** (RomM 5.4.1 or newer).
2. Press **Pair this device**: a QR code and a short code appear. Scan the QR code with your phone, sign in to RomM
   and approve; or open `<your RomM>/pair/device` in any browser and enter the short code. No password is ever
   typed on the device.
3. Sign in to SteamGridDB from the panel (it supplies the artwork), then press **Browse games**. Pick a game and
   press **Download**. Progress shows on the game, in the panel and on Steam's Downloads page; a download cut off
   by a restart continues by itself.

## Development

```sh
pnpm install
uv pip install --target py_modules --no-deps yt-dlp   # trailer previews (not kept in git)
pnpm typecheck && pnpm test && pnpm build   # types, frontend tests, dist/index.js (Vite)
uv run ruff check py_modules/boilerromm main.py tests && uv run pytest   # backend lint and tests
npx decky-toolkit dev   # deploy to a paired device and live-sync changes
```

See [docs/architecture.md](docs/architecture.md) for how it is put together, [src/steam/README.md](src/steam/README.md)
for every hook into Steam, and [docs/romm-api.md](docs/romm-api.md) for the RomM endpoints used.

## License

boilerRomM is free software under the GNU Affero General Public License, version 3 ([LICENSE](LICENSE)).

It started from the [Decky plugin template](https://github.com/SteamDeckHomebrew/decky-plugin-template), which is
BSD 3-Clause; that notice is kept in [LICENSES/BSD-3-Clause.txt](LICENSES/BSD-3-Clause.txt).
