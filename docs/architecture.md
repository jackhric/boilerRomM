# Architecture

ChickenTender shows a [RomM](https://romm.app) library inside Steam's Big Picture UI, downloads what you pick into
RetroDECK's ROM folder, and makes each installed game behave like a Steam game: a library entry, a row in
Settings > Storage, Uninstall, and Steam's Downloads page while it downloads.

## Principles

- **RomM is the catalogue.** The game list is fetched from RomM; the plugin keeps no copy of it.
- **The install ledger decides a game's state.** One record per game on this device (`installs.json`), with the
  files RomM listed and their sizes. The disk is only ever checked against it, so "installed" means every file is
  there in full, and a download cut off by a restart continues afterwards.
- **One state, one event.** The backend owns one snapshot (`App.state()`); every command returns it and every
  change pushes it as `chickentender_state`. Download progress goes out separately (`chickentender_progress`).
- **Steam is touched in one place.** Everything that reaches into Steam lives in `src/steam`, acts only on our own
  games and can be undone. See [src/steam/README.md](../src/steam/README.md).
- **Nothing secret typed on the device.** Pairing uses RomM's device code flow; the token lives in a 0600 file.

## Backend (`main.py`, `py_modules/chickentender/`)

`main.py` is the list of calls the frontend can make; each forwards to `App`. Nothing under `py_modules/` imports
`decky`, so the package runs in tests.

| Module | Owns |
| --- | --- |
| `app.py` | `App`: builds the rest, exposes the commands, emits the events |
| `settings.py` | the settings file: server, token, device id, ROM folder, SteamGridDB key |
| `jsonfile.py` | the one atomic JSON writer |
| `romm.py`, `pairing.py` | the RomM client and the device code flow |
| `library.py` | platforms and games from RomM, each with its state from the ledger |
| `ledger.py` | the install ledger: records, states, and the check of a record against the disk |
| `install.py` | where a game lives on disk: the ROM folder, the ES-DE folder for a platform |
| `downloads.py` | the download queue: one at a time, per-file `.part` with resume, every change written to the ledger |
| `shortcuts.py` | which Steam shortcut (appid) belongs to which game |
| `sgdb.py`, `artwork.py`, `signin.py`, `cdp.py` | SteamGridDB art, its cache, and "Sign in with Steam" for the key |
| `video.py` | trailer streams (runs the vendored `yt_dlp` from `py_modules/`; keep this file at this depth) |
| `retrodeck.py` | read-only view of the RetroDECK install |

Files on the device, all under Decky's settings and runtime folders for the plugin: `settings.json`,
`installs.json`, `shortcuts.json`, `sgdb/` (art cache), `icons/`, and `chickentender-launch`, which every Steam
shortcut runs. These paths, and the plugin's name they derive from, must not change: existing shortcuts and
records depend on them.

## Frontend (`src/`)

| Folder | What lives there | May import |
| --- | --- | --- |
| `api.ts`, `state.ts` | the backend's calls, events and types; hooks for the latest state and progress | `@decky/api` |
| `domain/` | pure logic: status and actions, formatting, the store's catalogue, routes | types from `api.ts` |
| `steam/` | every hook into Steam, behind `steam/index.ts` | `@decky/*` only |
| `app/` | use cases joining the backend and Steam: start-up, download, remove, shortcut repair | `api`, `domain`, `steam` |
| `ui/kit/` | shared components, tokens, art, backdrops, focus, video | `domain`, `api` types |
| `ui/store/`, `ui/game/`, `ui/panel/` | the store pages, the game page, the Quick Access panel | `kit`, `domain`, `app`, `api` |
| `index.tsx` | registers the routes and the panel, starts and stops `app` | `ui`, `app` |

## Checks

```sh
pnpm typecheck && pnpm test && pnpm build   # frontend: types, tests/{steam,domain,app}, bundle
uv run ruff check py_modules/chickentender main.py tests && uv run pytest   # backend
```

`tests/test_contract.py` fails when the frontend and backend disagree on a call name, an event name or the keys
of the state.
