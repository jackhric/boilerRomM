import sitemap from '@astrojs/sitemap';
import starlight from '@astrojs/starlight';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'astro/config';
import { statisticsHead } from './src/statistics.mjs';
import { fileURLToPath } from 'node:url';

const repo = 'https://github.com/jackhric/boilerRomM';
const ogImage = 'https://jackhric.github.io/boilerRomM/og.jpg';
const repoDocs = fileURLToPath(new URL('../docs/', import.meta.url));

// Pages such as the architecture notes render the repo's own docs/*.md. Their relative links point at files in the
// repo, which the site does not serve, so they are sent to GitHub instead, and their "# Title" is dropped because the
// docs page already shows one. Astro loads and compiles .md files itself, so this edits the compiled module, where
// the HTML sits in a JS string with escaped quotes.
function repoDocLinks() {
  const root = repoDocs.slice(0, -'docs/'.length);
  return {
    name: 'repo-doc-links',
    transform(code, id) {
      if (!id.startsWith(repoDocs) || !id.endsWith('.md')) return;
      return code
        .replace(/<h1 id=\\"[^"\\]*\\">.*?<\/h1>(\\n)?/, '')
        .replace(/href=\\"(?![a-z]+:|#)([^"\\]+)\\"/g, (_, href) =>
          `href=\\"${repo}/blob/main/${new URL(href, `file://${id}`).pathname.slice(root.length)}\\"`);
    },
  };
}

const building = process.argv.includes('build');

export default defineConfig({
  site: 'https://jackhric.github.io',
  base: '/boilerRomM',
  integrations: [
    sitemap(),
    starlight({
      title: 'boilerRomM',
      description: 'A Decky Loader plugin that turns your RomM server into a store inside Steam, and installs the emulators to play what you download.',
      components: { SiteTitle: './src/components/docs/SiteTitle.astro' },
      favicon: '/favicon.svg',
      social: [{ icon: 'github', label: 'GitHub', href: repo }],
      editLink: { baseUrl: `${repo}/edit/main/site/` },
      lastUpdated: true,
      customCss: ['./src/styles/docs.css'],
      head: [
        ...(building ? statisticsHead : []),
        { tag: 'meta', attrs: { property: 'og:image', content: ogImage } },
        { tag: 'meta', attrs: { property: 'og:image:width', content: '1200' } },
        { tag: 'meta', attrs: { property: 'og:image:height', content: '630' } },
        { tag: 'meta', attrs: { name: 'twitter:card', content: 'summary_large_image' } },
        { tag: 'meta', attrs: { name: 'twitter:image', content: ogImage } },
      ],
      sidebar: [
        { label: 'Start here', items: ['docs', 'docs/install', 'docs/setup', 'docs/faq'] },
        { label: 'Guides', items: ['docs/guides/store', 'docs/guides/emulators'] },
        { label: 'Reference', items: ['docs/reference/architecture'] },
      ],
    }),
  ],
  vite: {
    plugins: [tailwindcss(), repoDocLinks()],
    server: { fs: { allow: ['..'] } },
  },
});
