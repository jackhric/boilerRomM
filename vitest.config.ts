import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const stub = (name: string) => fileURLToPath(new URL(`tests/steam/stubs/${name}`, import.meta.url));

// Steam and Decky only exist on the device; the code is tested against stand-ins of the pieces it calls.
export default defineConfig({
  resolve: { alias: { "@decky/ui": stub("decky-ui.ts"), "@decky/api": stub("decky-api.ts") } },
  test: { include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"], setupFiles: [stub("setup.ts")] },
});
