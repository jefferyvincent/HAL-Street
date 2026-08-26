import { useEffect } from "react";
import { useConnection } from "@/stores/connection";

/** Opens the link for the lifetime of the app, and closes it on unmount. */
export function useConnect(): void {
  const connect = useConnection((s) => s.connect);
  useEffect(() => connect(), [connect]);
}
