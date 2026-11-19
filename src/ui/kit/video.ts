import { useEffect, useMemo, useState } from "react";
import { Game, GameDetails, gameVideo } from "../../api";

/** A plain video file, or YouTube's player; a file may name what to play when it cannot be loaded. */
export type VideoSource = { kind: "file"; src: string; /** The sound, when the file itself is silent. */ audio?: string; fallback?: VideoSource } | { kind: "youtube"; id: string };

type Streams = { small: string; large: string; audio: string };
const STREAMS_FRESH_MS = 2 * 3600 * 1000;
const streamCache = new Map<number, { at: number; streams: Streams }>();
const streamsInFlight = new Map<number, Promise<Streams>>();

function resolveStreams(romId: number): Promise<Streams> {
  const cached = streamCache.get(romId);
  if (cached && Date.now() - cached.at < STREAMS_FRESH_MS) return Promise.resolve(cached.streams);
  let p = streamsInFlight.get(romId);
  if (!p) {
    p = gameVideo(romId)
      .then(({ small, large, audio }) => ({ small, large, audio: audio ?? "" }))
      .catch(() => ({ small: "", large: "", audio: "" }))
      .then((streams) => {
        streamCache.set(romId, { at: Date.now(), streams });
        return streams;
      })
      .finally(() => streamsInFlight.delete(romId));
    streamsInFlight.set(romId, p);
  }
  return p;
}

let warming: Promise<unknown> = Promise.resolve();
/** Resolves the trailers of games about to be shown, one after another, so a preview can start at once. */
export function warmVideos(games: Game[]) {
  for (const g of games) warming = warming.then(() => resolveStreams(g.rom_id));
}

/** A stream address stopped working (they expire): resolve it again next time. */
export function videoBroke(src: string) {
  for (const [romId, entry] of streamCache) if (entry.streams.small === src || entry.streams.large === src) streamCache.delete(romId);
}

/**
 * The game's video as a plain file where possible: one RomM hosts, else the trailer's direct stream resolved by the
 * backend, with YouTube's player only as the fallback. Undefined while resolving and when the game has no video.
 */
export function useVideo(details: GameDetails | undefined, size: "small" | "large"): VideoSource | undefined {
  const romId = details?.rom_id;
  const embed = details?.youtube_video_id;
  const hosted = details?.video;
  const [resolved, setResolved] = useState<{ romId: number; streams: Streams }>();
  useEffect(() => {
    if (romId === undefined || hosted || !embed) return;
    let live = true;
    void resolveStreams(romId).then((streams) => live && setResolved({ romId, streams }));
    return () => {
      live = false;
    };
  }, [romId, hosted, embed]);
  return useMemo(() => {
    if (hosted) return { kind: "file", src: hosted };
    if (!embed || !resolved || resolved.romId !== romId) return undefined;
    const youtube: VideoSource = { kind: "youtube", id: embed };
    const src = size === "small" ? resolved.streams.small || resolved.streams.large : resolved.streams.large || resolved.streams.small;
    return src ? { kind: "file", src, audio: resolved.streams.audio || undefined, fallback: youtube } : youtube;
  }, [hosted, embed, resolved, romId, size]);
}
