import type { Decision, GateVerdict } from "@/types";

/** One row of the journal table or the tape, already counted. */
export interface Row {
  ts: string;
  decision: Decision;
  gates: GateVerdict[];
  failed: GateVerdict[];
  passedCount: number;
  total: number;
}

export const toRow = (d: Decision): Row => {
  const gates = d.gates ?? [];
  const failed = gates.filter((g) => !g.passed);
  return {
    ts: d.ts,
    decision: d,
    gates,
    failed,
    passedCount: gates.length - failed.length,
    total: gates.length,
  };
};

/** Newest first — the order both the tape and the table read in. */
export const newestFirst = (decisions: Decision[]): Row[] =>
  [...decisions].reverse().map(toRow);

/**
 * Resolve a selection against the current push.
 *
 * Held as a timestamp rather than an object reference or an index: every push
 * replaces the decision objects, so a reference would deselect on each update, and an
 * index would slide as records arrive. A null selection means "follow the newest",
 * which is a different thing from "the one that is newest right now".
 */
export const resolve = (decisions: Decision[], selected: string | null): Decision | null =>
  (selected ? decisions.find((d) => d.ts === selected) : undefined) ??
  decisions[decisions.length - 1] ??
  null;

/** The neighbours of the current selection, for the J/K keys. Null where there is none. */
export function neighbours(decisions: Decision[], current: Decision | null) {
  const i = current ? decisions.findIndex((d) => d.ts === current.ts) : -1;
  return {
    prev: i > 0 ? decisions[i - 1]!.ts : null,
    next: i >= 0 && i < decisions.length - 1 ? decisions[i + 1]!.ts : null,
  };
}

/** The three facts about a structure the console shows above the gate ledger. */
export interface Fact {
  /** Which fact this is. The words for it are looked up by the caller. */
  key: string;
  value: string;
  good?: boolean;
}

type Money = (v: string | number | null | undefined) => string;

/**
 * `money` and `dash` are passed in rather than imported: this file is pure, and the
 * dash a locale prints for "no figure" is one of its words.
 */
export function facts(d: Decision, money: Money, dash: string): Fact[] {
  const s = d.structure_detail ?? {};
  return [
    // A negative net is a credit — money received to open — so it reads as good.
    { key: "net", value: s.limit_price != null ? money(s.limit_price) : dash,
      good: Number(s.limit_price) < 0 },
    { key: "qty", value: String(s.qty ?? dash) },
    { key: "legs", value: String(s.legs?.length || dash) },
  ];
}
