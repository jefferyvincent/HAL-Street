import { isHeartbeat, type Push, type Snapshot } from "@/types";

/**
 * The transport. No React and no state of its own — it opens the link, hands what
 * arrives to the connection store, and can be closed.
 *
 * **This socket is never written to.** There is no `send` here, and there is none on
 * the server either — the endpoint pushes and never reads, so a frame from this side
 * would have nowhere to land. That is deliberate: a duplex channel is the one part of
 * this panel that could quietly become a second path to the broker, and the way it
 * stays read-only is that neither end has the code.
 *
 * The server pushes a full snapshot whenever the journal, ledger or circuit file
 * changes, and a heartbeat in between. The heartbeat is what makes a dropped
 * connection visible: nothing reads from the socket, so a silently dead one is
 * indistinguishable from a quiet market until a send fails.
 *
 * If the upgrade cannot be established at all, polling takes over. A panel showing
 * stale numbers because its transport is unfashionable is worse than one that polls.
 */

const RECONNECT_MS = 2000;
const POLL_MS = 5000;
/** Consecutive socket failures before giving up on it and polling instead. */
const GIVE_UP_AFTER = 3;

export type Transport = "socket" | "poll";

export interface LinkHandlers {
  onSnapshot: (s: Snapshot, via: Transport) => void;
  onAlive: () => void;
  onDrop: (reason: string) => void;
  onTransport: (via: Transport) => void;
}

/** Open the link. Returns the closer; calling it stops all retries. */
export function openLink(h: LinkHandlers): () => void {
  let socket: WebSocket | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let failures = 0;
  let closed = false;

  const poll = async () => {
    if (closed) return;
    try {
      const r = await fetch("/api/state", { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      h.onSnapshot((await r.json()) as Snapshot, "poll");
    } catch (e) {
      h.onDrop(e instanceof Error ? e.message : String(e));
    }
    timer = setTimeout(poll, POLL_MS);
  };

  const connect = () => {
    if (closed) return;
    if (failures >= GIVE_UP_AFTER) {
      h.onTransport("poll");
      void poll();
      return;
    }
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(`${proto}//${location.host}/ws`);

    socket.onopen = () => {
      failures = 0;
      h.onTransport("socket");
      h.onAlive();
    };
    socket.onmessage = (ev) => {
      const msg = JSON.parse(ev.data as string) as Push;
      if (isHeartbeat(msg)) h.onAlive();
      else h.onSnapshot(msg, "socket");
    };
    socket.onclose = () => {
      if (closed) return;
      failures += 1;
      h.onDrop("socket closed");
      timer = setTimeout(connect, RECONNECT_MS);
    };
    // onerror fires before onclose; letting onclose own the retry keeps one path.
    socket.onerror = () => socket?.close();
  };

  connect();
  return () => {
    closed = true;
    clearTimeout(timer);
    socket?.close();
  };
}
