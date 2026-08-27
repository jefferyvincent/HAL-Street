import { create } from "zustand";
import { openLink, type Transport } from "@/lib/ws";
import type { Marks, Snapshot } from "@/types";

/**
 * The run, as the server last sent it.
 *
 * Everything the panel draws comes from here, and nothing in the app writes to it
 * except the transport — the store has no action that edits a snapshot, only one that
 * replaces it wholesale with what arrived. There is no local mutation of a figure and
 * no optimistic update, because there is no operation to be optimistic about: the
 * panel cannot change anything it displays.
 */

interface Connection {
  snapshot: Snapshot | null;
  connected: boolean;
  transport: Transport | null;
  error: string | null;
  /** When the last push or poll landed — the footer's clock. */
  at: string | null;
  /**
   * Live marks, polled once for the whole app rather than per component.
   *
   * Two views want them — the holdings strip and the structure chart — and each
   * calling its own hook meant two independent timers and two MCP subprocess
   * spawns every interval, for one number. Held here so the broker is asked once.
   */
  marks: Marks | null;
  setMarks: (marks: Marks) => void;
  /** Opens the link. Returns the closer, for the effect that called it. */
  connect: () => () => void;
}

export const useConnection = create<Connection>((set) => ({
  snapshot: null,
  connected: false,
  transport: null,
  error: null,
  at: null,
  marks: null,
  setMarks: (marks) => set({ marks }),
  connect: () =>
    openLink({
      onSnapshot: (snapshot, transport) =>
        set({ snapshot, transport, connected: true, error: null, at: new Date().toISOString() }),
      onAlive: () => set({ connected: true, error: null, at: new Date().toISOString() }),
      onDrop: (error) => set({ connected: false, error }),
      onTransport: (transport) => set({ transport }),
    }),
}));

/** Selectors, so a component re-renders on the slice it reads and not on every tick. */
export const useSnapshot = () => useConnection((s) => s.snapshot);
