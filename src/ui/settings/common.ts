import { ConfirmModal, showModal } from "@decky/ui";
import { createElement } from "react";

/** A click handler for a backend call: a failure shows up in the state it changes, not here. */
export const run = (call: () => Promise<unknown>) => () => void call().catch(() => {});

export function confirm(title: string, description: string, okText: string, onOK: () => void) {
  showModal(createElement(ConfirmModal, { strTitle: title, strDescription: description, strOKButtonText: okText, onOK }));
}
