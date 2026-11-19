export const STORE_ROUTE = "/chickentender";
export const GAME_ROUTE = "/chickentender/game/:rom_id";
/** The route of one game's detail page. */
export const gameRoute = (rom_id: number) => `/chickentender/game/${rom_id}`;
export const CONSOLE_ROUTE = "/chickentender/console/:platform_id";
/** The route of one console's library page. */
export const consoleRoute = (platform_id: number) => `/chickentender/console/${platform_id}`;
