#!/usr/bin/env bash
# usage: make.sh
# Writes public/og.jpg (1200x630), the link-preview image: the Discover screenshot behind the wordmark.
# wordmark.svg is the wordmark as outlines (Space Grotesk 400 + 700), so it renders without the font installed.
set -euo pipefail
here=$(dirname "$0")
site=$here/../..
font=$site/../assets/fonts/SpaceGrotesk-latin.woff2
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT

magick "$site/src/assets/shots/hero.webp" -resize 860x -brightness-contrast -30x0 -background '#171d25' \
  -gravity east -extent 1200x630 "$tmp/shot.png"
magick -size 1200x630 xc:none -fill '#171d25' -draw 'rectangle 0,0 420,630' \
  \( -size 420x630 -define gradient:direction=east gradient:'#171d25'-'#171d2500' \) -geometry +420+0 -composite \
  "$tmp/shade.png"
magick -background none -density 400 "$here/wordmark.svg" -resize 520x "$tmp/wordmark.png"
magick "$tmp/shot.png" "$tmp/shade.png" -composite \
  "$tmp/wordmark.png" -gravity northwest -geometry +72+210 -composite \
  -font "$font" -fill '#acb2b8' -pointsize 40 -annotate +72+360 'Your RomM library,' \
  -annotate +72+410 'as a store in Steam' \
  -quality 85 "$site/public/og.jpg"
echo "wrote public/og.jpg"
