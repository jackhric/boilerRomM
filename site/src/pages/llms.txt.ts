import type { APIRoute } from 'astro';
import { getCollection } from 'astro:content';

const url = (site: URL, slug: string) => new URL(`${import.meta.env.BASE_URL.replace(/\/$/, '')}/${slug}/`, site).href;

export const GET: APIRoute = async ({ site }) => {
  const docs = (await getCollection('docs')).sort((a, b) => a.id.localeCompare(b.id));
  const link = (d: (typeof docs)[number]) => `- [${d.data.title}](${url(site!, d.id)}): ${d.data.description ?? ''}`;
  const body = [
    '# boilerRomM',
    '',
    '> boilerRomM is a free, open-source (AGPL-3.0) Decky Loader plugin that shows a self-hosted RomM library as a',
    "> store inside Steam's Game Mode on the Steam Deck and other SteamOS or Bazzite devices. Downloaded games become",
    "> Steam library entries with SteamGridDB artwork, appear on Steam's Downloads page and in Settings > Storage, and",
    '> launch in emulators the plugin installs and configures itself (RetroArch, PCSX2, Dolphin, Xenia Canary, RPCS3,',
    '> Cemu, shadPS4, Lichii, KytyPS5), with BIOS and firmware taken from the user\'s own RomM server. It ships no',
    '> games, BIOS or keys. It is in development and has no release yet.',
    '',
    '## Docs',
    '',
    ...docs.map(link),
    '',
    '## Optional',
    '',
    '- [Source (GitHub)](https://github.com/jackhric/boilerRomM)',
    '- [RomM](https://romm.app)',
    '',
  ];
  return new Response(body.join('\n'), { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
};
