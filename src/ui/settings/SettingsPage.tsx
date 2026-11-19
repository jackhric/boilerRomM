import { SidebarNavigation, SteamSpinner } from "@decky/ui";
import { FaGamepad, FaHdd, FaInfoCircle, FaMicrochip, FaServer } from "react-icons/fa";
import { settingsPages, useTransparentHeader } from "../../steam";
import { useBackendState } from "../../state";
import { Guard } from "../kit/guard";
import { About } from "./About";
import { Bios } from "./Bios";
import { Emulators } from "./Emulators";
import { Server } from "./Server";
import { Storage } from "./Storage";

function Settings() {
  useTransparentHeader();
  const state = useBackendState();
  if (!state) return <SteamSpinner />;
  return (
    <SidebarNavigation
      pages={settingsPages([
        { title: "Emulators", icon: <FaGamepad />, content: <Emulators state={state} />, identifier: "emulators" },
        { title: "Server", icon: <FaServer />, content: <Server state={state} />, identifier: "server" },
        { title: "BIOS", icon: <FaMicrochip />, content: <Bios state={state} />, identifier: "bios" },
        { title: "Storage", icon: <FaHdd />, content: <Storage state={state} />, identifier: "storage" },
      ], [
        { title: "About", icon: <FaInfoCircle />, content: <About state={state} />, identifier: "about" },
      ])}
    />
  );
}

export function SettingsPage() {
  return <Guard what="the settings"><Settings /></Guard>;
}
