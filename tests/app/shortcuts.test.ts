import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Install } from "../../src/api";
import { shortcutRepair } from "../../src/app/shortcuts";

const install = (over: Partial<Install>): Install => ({
  rom_id: 1, name: "G", state: "installed", appid: 0x90000001, bytes_done: 1, bytes_total: 1, missing: [], error: "", queued_at: 0, updated_at: 0, completed_at: 0, ...over,
});

describe("shortcut repair", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  const setup = (installs: Install[], has: (appid: number) => boolean | undefined) => {
    const steam = { hasShortcut: vi.fn(has), prepare: vi.fn(async () => 1), forget: vi.fn(async () => undefined) };
    const repair = shortcutRepair(() => installs, steam);
    return { steam, repair };
  };

  it("waits for a new shortcut to settle, then recreates one that is gone", async () => {
    const { steam, repair } = setup([install({})], () => false);
    repair.check();
    await vi.advanceTimersByTimeAsync(4000);
    expect(steam.prepare).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1500);
    expect(steam.prepare).toHaveBeenCalledWith(1);
  });

  it("does nothing while Steam's app list has not loaded, or when the shortcut is there", async () => {
    for (const has of [() => undefined, () => true]) {
      const { steam, repair } = setup([install({})], has);
      repair.check();
      await vi.advanceTimersByTimeAsync(6000);
      expect(steam.prepare).not.toHaveBeenCalled();
      expect(steam.forget).not.toHaveBeenCalled();
    }
  });

  it("forgets a stale appid of a game that needs no shortcut, and leaves one without an appid alone", async () => {
    const { steam, repair } = setup([install({ rom_id: 2, state: "incomplete" }), install({ rom_id: 3, state: "failed", appid: 0 })], () => false);
    repair.check();
    await vi.advanceTimersByTimeAsync(6000);
    expect(steam.forget).toHaveBeenCalledTimes(1);
    expect(steam.forget).toHaveBeenCalledWith(2);
    expect(steam.prepare).not.toHaveBeenCalled();
  });

  it("gives up on a game after two tries, and stop cancels a pending check", async () => {
    const { steam, repair } = setup([install({})], () => false);
    for (let i = 0; i < 4; i++) {
      repair.check();
      await vi.advanceTimersByTimeAsync(6000);
    }
    expect(steam.prepare).toHaveBeenCalledTimes(2);
    repair.check();
    repair.stop();
    await vi.advanceTimersByTimeAsync(6000);
    expect(steam.prepare).toHaveBeenCalledTimes(2);
  });
});
