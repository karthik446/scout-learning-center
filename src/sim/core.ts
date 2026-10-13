/* Scout learning center simulator: the part shared by the page block and the headless golden runner.
 * No DOM, no timers, no Math.random, no Date: given a scenario and a seed it replays identically.
 * Wraps the vendored Breakscale engine (MIT; vendor/breakscale, pinned in UPSTREAM.txt). */
import { Engine } from '../../vendor/breakscale/engine';
import type { SimSnapshot, Topology } from '../../vendor/breakscale/types';

export { Engine };
export type { SimSnapshot, Topology };

export interface Knob { id: string; label: string; node: string; field: string; min: number; max: number; step: number; default: number; unit: string }
/** A fault knob: a button that crashes one node and restores it. */
export interface FaultKnob { id: string; label: string; node: string; kind: 'crash' }
export interface Assertion {
  id: string;
  knobs: Record<string, number>;
  faults?: string[];
  settle_s?: number;
  window_s?: number;
  metric: string;
  op: '>' | '>=' | '<' | '<=' | 'between';
  value: number | [number, number];
}
export interface Scenario {
  schema_version: string;
  id: string;
  title: string;
  seed: number;
  warmup_s: number;
  window_s: number;
  scale_note: string | null;
  nodes: Topology['nodes'];
  edges: Topology['edges'];
  knobs: Knob[];
  faults?: FaultKnob[];
  readouts: string[];
  assertions: Assertion[];
}

/** The engine clamps one advance() to 100 ms; the app and its tests step it at 60 Hz. */
export const FRAME_MS = 1000 / 60;
/** Every readout is a mean over this many simulated seconds, the same window for offered and goodput. */
export const READOUT_WINDOW_S = 5;

export class Sim {
  engine: Engine;
  readonly active = new Set<string>();
  constructor(public readonly sc: Scenario) {
    this.engine = new Engine({ nodes: sc.nodes, edges: sc.edges }, sc.seed);
    for (const k of sc.knobs) this.setKnob(k.id, k.default);
  }
  setKnob(id: string, value: number): void {
    const k = this.sc.knobs.find((x) => x.id === id);
    if (!k) throw new Error('unknown knob ' + id);
    this.engine.updateNodeConfig(k.node, { [k.field]: value });
  }
  setFault(id: string, on: boolean): void {
    const f = (this.sc.faults || []).find((x) => x.id === id);
    if (!f) throw new Error('unknown fault ' + id);
    if (on) { this.engine.injectFailure(f.node, f.kind); this.active.add(id); }
    else { this.engine.clearFailure(f.node); this.active.delete(id); }
  }
  step(ms: number): void {
    let left = ms;
    while (left > 1e-9) { const d = Math.min(FRAME_MS, left); this.engine.advance(d); left -= d; }
  }
  snapshot(): SimSnapshot { return this.engine.snapshot(); }
}

export const METRIC_NAMES = ['p50', 'p95', 'p99', 'goodput', 'offered', 'errors'];
export const NODE_METRIC_NAMES = ['util', 'queue', 'arrival', 'shed', 'timeout', 'hit', 'throttled', 'rejected', 'breaker', 'stale', 'lag'];
const BREAKER_NUM: Record<string, number> = { closed: 0, 'half-open': 0.5, open: 1 };

/** One number for a readout key. Percentiles in ms, rates per second, fractions 0..1, breaker 0 closed / 0.5 half-open / 1 open. */
export function readValue(snap: SimSnapshot, key: string): number {
  const [name, node] = key.split(':');
  const sys = snap.system;
  switch (name) {
    case 'p50': return sys.p50;
    case 'p95': return sys.p95;
    case 'p99': return sys.p99;
    case 'goodput': return sys.goodputRps;
    case 'offered': return sys.offeredRps;
    case 'errors': return sys.errorRate;
  }
  const n = node ? snap.nodes[node] : undefined;
  if (!n) return NaN;
  switch (name) {
    case 'util': return n.utilization;
    case 'queue': return n.queued;
    case 'arrival': return n.arrivalRate;
    case 'shed': return n.shedRate;
    case 'timeout': return n.timeoutRate;
    case 'hit': return n.hitRate;
    case 'throttled': return n.throttledRate ?? 0;
    case 'rejected': return n.rejectedRate ?? 0;
    case 'breaker': return BREAKER_NUM[n.breakerState ?? 'closed'];
    case 'stale': return n.staleReadRate;
    case 'lag': return n.consumerLag ?? 0;
  }
  return NaN;
}

/** The metric keys a scenario reads anywhere: readouts plus assertion metrics, plus offered and goodput always. */
export function keysOf(sc: Scenario): string[] {
  return Array.from(new Set(['offered', 'goodput', ...sc.readouts, ...sc.assertions.map((a) => a.metric)]));
}

/** Trailing means over simulated time. `goodput` is capped at `offered` (see capGoodput). */
export class Meter {
  private rows: { t: number; v: Float64Array }[] = [];
  constructor(private keys: string[], private windowS: number) {}
  sample(snap: SimSnapshot): void {
    const t = snap.system.timeMs / 1000;
    const v = new Float64Array(this.keys.length);
    this.keys.forEach((k, i) => { v[i] = readValue(snap, k); });
    this.rows.push({ t, v });
    const cut = t - this.windowS;
    while (this.rows.length > 1 && this.rows[0].t < cut) this.rows.shift();
  }
  clear(): void { this.rows = []; }
  raw(key: string): number {
    const i = this.keys.indexOf(key);
    if (i < 0 || !this.rows.length) return NaN;
    let s = 0;
    for (const r of this.rows) s += r.v[i];
    return s / this.rows.length;
  }
  mean(key: string): number {
    const m = this.raw(key);
    return key === 'goodput' ? capGoodput(m, this.raw('offered')) : m;
  }
}

/**
 * Goodput is completions of requests that succeeded, offered is arrivals, and both come from 1-second rate counters:
 * over one window completions can read a few percent above arrivals by sampling noise alone (the spike showed
 * 207 of 204 offered). Both are therefore means over the same window, and the goodput we show and quote is capped at
 * the offered mean, so the page can never print a goodput larger than the load that was offered.
 */
export function capGoodput(good: number, offered: number): number {
  return Number.isFinite(offered) ? Math.min(good, offered) : good;
}

export function compare(a: Assertion, got: number): boolean {
  switch (a.op) {
    case '>': return got > (a.value as number);
    case '>=': return got >= (a.value as number);
    case '<': return got < (a.value as number);
    case '<=': return got <= (a.value as number);
    case 'between': { const [lo, hi] = a.value as [number, number]; return got >= lo && got <= hi; }
  }
}

export interface RunResult { metrics: Record<string, number>; sim: Sim }

/** Run one set of knob/fault settings: warm-up with nothing faulted, inject faults, settle, then sample once a second over the window. */
export function runWindow(sc: Scenario, knobs: Record<string, number>, faults: string[], settleS: number, windowS: number, keys: string[]): RunResult {
  const sim = new Sim(sc);
  for (const [id, v] of Object.entries(knobs)) sim.setKnob(id, v);
  sim.step(sc.warmup_s * 1000);
  for (const f of faults) sim.setFault(f, true);
  sim.step(settleS * 1000);
  const meter = new Meter(keys, windowS + 1);
  for (let s = 0; s < windowS; s += 1) { sim.step(1000); meter.sample(sim.snapshot()); }
  const metrics: Record<string, number> = {};
  for (const k of keys) metrics[k] = meter.mean(k);
  return { metrics, sim };
}

export interface Row { assertion: string; knobs: Record<string, number>; faults: string[]; metric: string; op: string; value: number | [number, number]; metrics: Record<string, number>; got: number; pass: boolean }

export function runAssertion(sc: Scenario, a: Assertion): Row {
  const keys = keysOf(sc);
  const faults = a.faults || [];
  const { metrics } = runWindow(sc, a.knobs, faults, a.settle_s ?? 0, a.window_s ?? sc.window_s, keys);
  const got = metrics[a.metric];
  return { assertion: a.id, knobs: a.knobs, faults, metric: a.metric, op: a.op, value: a.value, metrics, got, pass: Number.isFinite(got) && compare(a, got) };
}
