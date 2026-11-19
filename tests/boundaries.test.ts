import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve, dirname } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = resolve(__dirname, "../src");
const files = (dir: string): string[] =>
  readdirSync(dir).flatMap((n) => (statSync(join(dir, n)).isDirectory() ? files(join(dir, n)) : /\.tsx?$/.test(n) ? [join(dir, n)] : []));
const all = files(SRC).map((path) => ({ path: relative(SRC, path), text: readFileSync(path, "utf-8") }));
const imports = (text: string) => [...text.matchAll(/(?:from|import)\s+"([^"]+)"/g)].map((m) => m[1]);
/** A relative import as a path under src. */
const target = (from: string, spec: string) => relative(SRC, resolve(SRC, dirname(from), spec));

describe("layers", () => {
  it("only src/steam touches Steam itself", () => {
    const steamOnly = /\bSteamClient\b|\bappStore\b|\bappDetailsStore\b|\bdownloadsStore\b|\binstallFolderStore\b|\bcollectionStore\b|afterPatch|replacePatch|findModuleExport/;
    const offenders = all.filter((f) => !f.path.startsWith("steam/") && steamOnly.test(f.text)).map((f) => f.path);
    expect(offenders).toEqual([]);
  });

  it("the rest of the app enters src/steam through its index only", () => {
    const offenders = all
      .filter((f) => !f.path.startsWith("steam/"))
      .flatMap((f) => imports(f.text).filter((s) => s.startsWith(".")).map((s) => [f.path, target(f.path, s)]))
      .filter(([, to]) => to.startsWith("steam/"));
    expect(offenders).toEqual([]);
  });

  it("src/steam imports nothing from the rest of the app", () => {
    const offenders = all
      .filter((f) => f.path.startsWith("steam/"))
      .flatMap((f) => imports(f.text).filter((s) => s.startsWith(".")).map((s) => [f.path, target(f.path, s)]))
      .filter(([, to]) => !to.startsWith("steam"));
    expect(offenders).toEqual([]);
  });

  it("src/domain is plain logic: no React, no Decky, no UI, and only types from the backend", () => {
    const domain = all.filter((f) => f.path.startsWith("domain/"));
    const offenders = domain.flatMap((f) => imports(f.text).filter((s) => !s.startsWith("./")).map((s) => [f.path, s])).filter(([, s]) => s !== "../api");
    expect(offenders).toEqual([]);
    expect(domain.filter((f) => /^import \{[^}]*\} from "\.\.\/api"/m.test(f.text)).map((f) => f.path)).toEqual([]);
  });

  it('the word "Deck" appears only in the names of other projects', () => {
    const allowed = /Decky|decky|SteamDeckHomebrew|Steam Deck Homebrew/g;
    const offenders = all.filter((f) => /deck/i.test(f.text.replace(allowed, ""))).map((f) => f.path);
    expect(offenders).toEqual([]);
  });
});
