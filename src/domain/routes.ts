export const STORE_ROUTE = "/boilerromm";
export const GAME_ROUTE = "/boilerromm/game/:rom_id";
/** The route of one game's detail page. */
export const gameRoute = (rom_id: number) => `/boilerromm/game/${rom_id}`;
export const CONSOLE_ROUTE = "/boilerromm/console/:platform_id";
/** The route of one console's library page. */
export const consoleRoute = (platform_id: number) => `/boilerromm/console/${platform_id}`;
