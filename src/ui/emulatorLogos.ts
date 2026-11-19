// Emulator logos (assets/emulators, one PNG per emulator id), inlined into the bundle. Each belongs to its project.
const files = import.meta.glob<string>("../../assets/emulators/*.png", { eager: true, query: "?inline", import: "default" });

const byId = new Map(Object.entries(files).map(([path, src]) => [path.slice(path.lastIndexOf("/") + 1, -4), src]));

/** The logo of an emulator by id, as a data URL, or "" when there is none. */
export const emulatorLogo = (id: string): string => byId.get(id) ?? "";
