import { ConfirmModal, Menu, MenuItem, Navigation, showContextMenu, showModal } from "@decky/ui";
import { createElement, useCallback, useState } from "react";
import { Game } from "../../api";
import { download, play, removeFromDevice, stopDownload } from "../../app/games";
import { ACTION_LABELS, actionKind, canRemove } from "../../domain/status";

function confirmRemove(game: Game) {
  showModal(
    createElement(ConfirmModal, {
      strTitle: game.name,
      strDescription: "Remove this game from the device? Its files and its Steam shortcut are deleted; the game stays on your RomM server.",
      strOKButtonText: "Remove",
      bDestructiveWarning: true,
      onOK: () => void removeFromDevice(game.rom_id).catch(() => {}),
    }),
  );
}

/** The one primary action of a game (Download, Resume, Stop, Play) and its secondary menu. */
export function useGameActions(game: Game, serverUrl = "") {
  const [pending, setPending] = useState(false);
  const kind = actionKind(game);
  const act = useCallback(() => {
    const run = kind === "play" ? play(game.rom_id, game.name) : kind === "stop" ? stopDownload(game.rom_id) : download(game.rom_id);
    setPending(true);
    void Promise.resolve(run).catch(() => {}).finally(() => setPending(false));
  }, [game, kind]);
  const openMenu = useCallback((target?: any) => {
    const items = [
      createElement(MenuItem, { key: "act", onSelected: act }, ACTION_LABELS[kind]),
      canRemove(game) && createElement(MenuItem, { key: "remove", tone: "destructive", onSelected: () => confirmRemove(game) }, "Remove from this device"),
      serverUrl && createElement(MenuItem, { key: "romm", onSelected: () => Navigation.NavigateToExternalWeb(`${serverUrl.replace(/\/$/, "")}/rom/${game.rom_id}`) }, "Open in RomM"),
    ].filter(Boolean);
    showContextMenu(createElement(Menu, { label: game.name }, items), target?.currentTarget ?? target ?? window);
  }, [game, kind, act, serverUrl]);
  return { kind, label: ACTION_LABELS[kind], act, pending, openMenu };
}
