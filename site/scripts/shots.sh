#!/usr/bin/env bash
# usage: shots.sh [slot ...]
# Turns the publishable captures in media/shots/ (never media/shots/raw/) into the site's named slots in
# src/assets/shots/<slot>.webp. Each slot is cut to the plugin's own page: the crop drops Steam's top bar, where the
# account avatar sits, and the button hints at the bottom.
set -euo pipefail
cd "$(dirname "$0")/.."
src=../media/shots
out=src/assets/shots
mkdir -p "$out"

# slot | capture in media/shots | crop (WxH+X+Y on the 1920x1080 frame) | regions to blur first, space-separated
slots=(
  "hero|01-discover-spotlight-super-metroid.jpg|1920x960+0+60|"
  "browse|06-browse-grid-top.jpg|1920x960+0+60|"
  "game|11-game-wind-waker-top.jpg|1920x960+0+60|"
  "consoles|09-consoles.jpg|1920x960+0+60|"
  "setup|38-setup-installing-firmware.jpg|1920x960+0+60|"
  "pair|34-setup-pair-qr.jpg|1920x960+0+60|"
  "emulators|15-settings-emulators-top.jpg|1920x960+0+60|"
  "bios|17-settings-bios-files.jpg|1920x960+0+60|"
  "downloads|20-steam-downloads-active.jpg|1920x960+0+60|"
  "library|25-steam-library-non-steam.jpg|1920x960+0+60|"
  # Steam's Storage page lists every game on the drive; the rows above boilerRomM's and the drive's name are blurred.
  "storage|27-steam-storage-games.jpg|1536x768+384+252|1500x400+400+420 440x60+770+160"
)

for entry in "${slots[@]}"; do
  IFS='|' read -r slot file crop blur <<<"$entry"
  if [ $# -gt 0 ] && [[ " $* " != *" $slot "* ]]; then continue; fi
  if [ ! -f "$src/$file" ]; then echo "skip $slot: no $src/$file"; continue; fi
  regions=()
  for r in $blur; do regions+=(-region "$r" -blur 0x18 +region); done
  magick "$src/$file" "${regions[@]}" -crop "$crop" +repage -resize '1600x>' -quality 82 "$out/$slot.webp"
  echo "$slot <- $file"
done
