/**
 * The structure's name without a leading ticker, so it is never printed twice.
 *
 * Names built after the root was added begin with it; older ones do not. Every view
 * shows the underlying from its own field either way, and this keeps
 * "QQQ QQQ 2026-10-16 ..." from happening on the new ones.
 *
 * Not a rewrite of the record: the ledger keeps the name it was opened under, and
 * this is display only.
 */
export const stripRoot = (name: string, root: string): string =>
  name.startsWith(`${root} `) ? name.slice(root.length + 1) : name;
