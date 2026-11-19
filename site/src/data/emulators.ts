// Mirrors py_modules/boilerromm/emulators: the same order (oldest system first), systems and firmware.
export interface Emulator {
  name: string;
  systems: string;
  firmware: string | null;
  source: string;
}

export const emulators: Emulator[] = [
  {
    name: 'RetroArch',
    systems: 'NES, SNES, N64, Game Boy, GBA, Virtual Boy, Genesis, Master System, Sega CD, 32X, Saturn, PlayStation, Atari, Lynx, Jaguar, Neo Geo Pocket, WonderSwan, 3DO',
    firmware: 'Saturn, Sega CD and 3DO need a BIOS',
    source: 'libretro buildbot',
  },
  { name: 'PCSX2', systems: 'PlayStation 2', firmware: 'PS2 BIOS', source: 'PCSX2/pcsx2' },
  { name: 'Dolphin', systems: 'GameCube and Wii', firmware: null, source: 'pkgforge-dev/Dolphin-emu-AppImage' },
  { name: 'Xenia Canary', systems: 'Xbox 360', firmware: null, source: 'xenia-canary/xenia-canary' },
  { name: 'RPCS3', systems: 'PlayStation 3', firmware: 'PS3 system software', source: 'RPCS3/rpcs3-binaries-linux' },
  { name: 'Cemu', systems: 'Wii U', firmware: 'Keys only for disc images', source: 'cemu-project/Cemu' },
  { name: 'shadPS4', systems: 'PlayStation 4', firmware: 'PS4 system modules', source: 'shadps4-emu/shadPS4' },
  { name: 'Lichii', systems: 'Nintendo Switch and Switch 2', firmware: 'Console keys', source: 'zortos293/Lichii' },
  { name: 'KytyPS5', systems: 'PlayStation 5', firmware: null, source: 'KytyPS5/KytyPS5' },
];
