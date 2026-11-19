// Backend error text turned into a title a person can act on. The raw text stays available as the detail line.
export type ProblemKind = "unreachable" | "signed-out" | "server" | "other";
export interface Problem { kind: ProblemKind; title: string; detail: string }

const UNREACHABLE = /cannot connect|can't connect|connection (refused|reset|closed|error)|name resolution|name or service|getaddrinfo|unreachable|timed? ?out|timeout|ssl|certificate|no route|network is down|cannot reach|nothing answered/i;
const SIGNED_OUT = /no longer accepts this device|unauthori[sz]ed|forbidden|\b40[13]\b/i;
const SERVER_FAULT = /\b5\d\d\b|bad gateway|service unavailable|internal server error/i;

const TITLES: Record<ProblemKind, string> = {
  unreachable: "Can't reach your RomM server",
  "signed-out": "RomM signed this device out",
  server: "Your RomM server had a problem",
  other: "Something went wrong",
};

export function describeProblem(raw: string | undefined | null): Problem {
  const detail = (raw ?? "").trim();
  const kind: ProblemKind = SIGNED_OUT.test(detail) ? "signed-out" : SERVER_FAULT.test(detail) ? "server" : UNREACHABLE.test(detail) ? "unreachable" : "other";
  return { kind, title: TITLES[kind], detail };
}
