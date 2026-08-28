import { DiscoveryHeat } from "@/components/DiscoveryHeat";

/**
 * The universe the agent chose for itself, and everything it passed over choosing it.
 *
 * Its own tab rather than a card on the console: a census names sixty to eighty
 * symbols, and the console is where someone watches one position and one decision.
 */
export function DiscoveryView() {
  return <DiscoveryHeat />;
}
