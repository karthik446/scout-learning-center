/* Scout learning center: the simulator block. Plain TypeScript, no framework, one ES module (assets/sim/sim.js).
 * Finds every [data-scenario] host, fetches its scenario JSON from our own origin (the only request it makes),
 * runs the vendored Breakscale engine in the page and draws it: an SVG topology with moving request dots, queue
 * bars and saturated/crashed badges, a hand-drawn canvas chart, text readouts, labelled range knobs, fault
 * buttons, Pause and Reset. prefers-reduced-motion: no animation loop, the model steps once a second. */
import { FRAME_MS, Meter, READOUT_WINDOW_S, Sim, keysOf } from './core';
import type { Scenario, SimSnapshot } from './core';

const NODE_W = 120, NODE_H = 58, COL = 170, ROW = 104, PAD = 20, BAR_GAP = 8, BAR_H = 8;
const VNODE_W = 150, VNODE_H = 52, VROW = 96;
const NARROW_PX = 520;
const SAMPLE_MS = 250;
const CHART_S = 60;

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls?: string, text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}
function svgEl<K extends keyof SVGElementTagNameMap>(tag: K, attrs: Record<string, string | number>): SVGElementTagNameMap[K] {
  const e = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  return e;
}
const fmtMs = (v: number): string => (v >= 1000 ? (v / 1000).toFixed(2) + ' s' : Math.round(v) + ' ms');
const fmtPct = (v: number): string => (v > 0 && v < 0.1 ? (v * 100).toFixed(1) : String(Math.round(v * 100))) + '%';
const fmtRate = (v: number): string => Math.round(v) + ' /s';

const LABELS: Record<string, string> = {
  p50: 'Median latency (p50)', p95: 'p95 latency', p99: 'p99 latency', offered: 'Offered load', goodput: 'Goodput', errors: 'Failed',
  util: 'Utilisation', queue: 'Queue depth', arrival: 'Arrivals', shed: 'Shed', timeout: 'Timeouts', hit: 'Hit rate',
  throttled: 'Throttled', rejected: 'Rejected fast', breaker: 'Circuit', stale: 'Stale reads', lag: 'Consumer lag',
};

interface Pt { t: number; p99: number; good: number; offered: number }

class Block {
  sim: Sim;
  meter: Meter;
  keys: string[];
  reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  running = true;
  visible = true;
  vertical = false;
  last = 0;
  sinceSample = 0;
  dots: { edge: number; t: number }[] = [];
  hist: Pt[] = [];
  nodeRect = new Map<string, SVGRectElement>();
  nodeBadge = new Map<string, SVGTextElement>();
  nodeQueue = new Map<string, SVGRectElement>();
  edgeLine: { from: [number, number]; to: [number, number] }[] = [];
  dotLayer!: SVGGElement;
  canvas!: HTMLCanvasElement;
  readouts = new Map<string, HTMLElement>();
  status!: HTMLElement;
  figure!: HTMLElement;
  faultBtn = new Map<string, HTMLButtonElement>();
  knobInput = new Map<string, HTMLInputElement>();
  timer = 0;

  constructor(public root: HTMLElement, public sc: Scenario) {
    this.sim = new Sim(sc);
    this.keys = keysOf(sc);
    this.meter = new Meter(this.keys, READOUT_WINDOW_S);
    this.vertical = root.clientWidth > 0 && root.clientWidth < NARROW_PX;
    this.build();
    this.warm();
    if ('IntersectionObserver' in window) {
      new IntersectionObserver((es) => { this.visible = es[es.length - 1].isIntersecting; }).observe(root);
    }
    if (this.reduced) {
      // Static frames: step on a slow timer, no dots, no animation loop.
      this.timer = window.setInterval(() => { if (this.running && this.visible) { this.advance(1000); this.draw(); } }, 1000);
    } else {
      requestAnimationFrame((t) => this.frame(t));
    }
    if ('ResizeObserver' in window) {
      new ResizeObserver(() => {
        const v = root.clientWidth > 0 && root.clientWidth < NARROW_PX;
        if (v !== this.vertical) { this.vertical = v; this.buildFigure(); this.draw(); }
      }).observe(root);
    }
  }

  nodeLabel(id: string): string { return this.sc.nodes.find((n) => n.id === id)?.label ?? id; }
  keyLabel(key: string): string { const [name, node] = key.split(':'); return (LABELS[name] || name) + (node ? ' (' + this.nodeLabel(node) + ')' : ''); }

  build(): void {
    const sc = this.sc, root = this.root;
    root.textContent = '';
    root.classList.add('sim-block');
    root.append(el('h3', 'sim-title', sc.title));
    if (sc.scale_note) root.append(el('p', 'sim-scale', 'Scaled model: ' + sc.scale_note));
    this.status = el('p', 'sim-status', 'Simulation running. Seed ' + sc.seed + '. Readouts are ' + READOUT_WINDOW_S + '-second means.');
    this.status.setAttribute('role', 'status');
    this.figure = el('div', 'sim-figure');
    root.append(this.status, this.figure);
    this.buildFigure();

    const chartWrap = el('div', 'sim-chart-wrap');
    const c = el('canvas', 'sim-chart');
    c.width = 640; c.height = 180;
    c.setAttribute('role', 'img');
    c.setAttribute('aria-label', 'Last ' + CHART_S + ' seconds: p99 latency, goodput and offered load. The readouts give the current values as text.');
    chartWrap.append(c, el('p', 'sim-legend', 'Chart, last ' + CHART_S + ' s: solid line = p99 latency (left axis, ms). Dashed line = goodput, dotted line = offered load (right axis, requests per second).'));
    this.canvas = c;
    root.append(chartWrap);

    const form = el('form', 'sim-knobs');
    form.addEventListener('submit', (ev) => ev.preventDefault());
    for (const k of sc.knobs) {
      const row = el('div', 'sim-knob');
      const id = 'knob-' + sc.id + '-' + k.id;
      const lab = el('label', '', k.label);
      lab.htmlFor = id;
      const input = el('input');
      input.type = 'range'; input.id = id; input.min = String(k.min); input.max = String(k.max); input.step = String(k.step); input.value = String(k.default);
      const out = el('output', '', String(k.default) + k.unit);
      out.htmlFor.add(id);
      input.addEventListener('input', () => {
        const v = Number(input.value);
        out.textContent = String(v) + k.unit;
        this.sim.setKnob(k.id, v);
        this.status.textContent = k.label + ' set to ' + v + k.unit + '.';
      });
      this.knobInput.set(k.id, input);
      row.append(lab, input, out);
      form.append(row);
    }
    const btns = el('div', 'sim-buttons');
    for (const f of sc.faults || []) {
      const b = el('button', 'sim-fault');
      b.type = 'button';
      b.setAttribute('aria-pressed', 'false');
      b.textContent = f.label;
      b.addEventListener('click', () => {
        const on = !this.sim.active.has(f.id);
        this.sim.setFault(f.id, on);
        b.setAttribute('aria-pressed', String(on));
        b.textContent = on ? 'Restore ' + this.nodeLabel(f.node) : f.label;
        this.status.textContent = on ? this.nodeLabel(f.node) + ' crashed: calls to it now fail.' : this.nodeLabel(f.node) + ' restored.';
        this.draw();
      });
      this.faultBtn.set(f.id, b);
      btns.append(b);
    }
    const pause = el('button', '', 'Pause');
    pause.type = 'button';
    pause.addEventListener('click', () => {
      this.running = !this.running;
      pause.textContent = this.running ? 'Pause' : 'Run';
      this.status.textContent = this.running ? 'Simulation running.' : 'Simulation paused.';
    });
    const reset = el('button', '', 'Reset');
    reset.type = 'button';
    reset.addEventListener('click', () => {
      this.sim = new Sim(sc);
      for (const k of sc.knobs) {
        const i = this.knobInput.get(k.id)!;
        i.value = String(k.default);
        i.dispatchEvent(new Event('input'));
      }
      for (const f of sc.faults || []) { const b = this.faultBtn.get(f.id)!; b.setAttribute('aria-pressed', 'false'); b.textContent = f.label; }
      this.meter.clear(); this.hist = []; this.dots = [];
      this.warm();
      this.status.textContent = 'Reset to the scenario defaults, seed ' + sc.seed + '.';
    });
    btns.append(pause, reset);
    form.append(btns);
    root.append(form);
    root.append(el('p', 'sim-attrib', 'Simulation engine: Breakscale (MIT, the Breakscale contributors), commit d2c876e0, vendored without its interface, analytics or link store. Nothing leaves this page.'));
  }

  /** (Re)draw the SVG picture and the readout list; horizontal on a wide block, one column when narrow. */
  buildFigure(): void {
    const sc = this.sc, v = this.vertical;
    this.figure.textContent = '';
    this.nodeRect.clear(); this.nodeBadge.clear(); this.nodeQueue.clear(); this.edgeLine = []; this.readouts.clear();
    const nw = v ? VNODE_W : NODE_W, nh = v ? VNODE_H : NODE_H;
    const maxX = Math.max(...sc.nodes.map((n) => n.x)), maxY = Math.max(...sc.nodes.map((n) => n.y));
    const w = v ? PAD * 2 + nw + maxY * (nw + 20) : PAD * 2 + nw + maxX * COL;
    const h = v ? PAD + (maxX + 1) * VROW : PAD + nh + BAR_GAP + BAR_H + maxY * ROW + 10;
    const svg = svgEl('svg', { viewBox: `0 0 ${w} ${h}`, class: 'sim-svg' + (v ? ' sim-svg-v' : ''), role: 'img', 'aria-label': 'Topology: ' + sc.nodes.map((n) => n.label).join(', then ') + '.' });
    const pos = new Map<string, [number, number]>();
    for (const n of sc.nodes) pos.set(n.id, v ? [PAD + n.y * (nw + 20), 10 + n.x * VROW] : [PAD + n.x * COL, 10 + n.y * ROW]);
    for (const e of sc.edges) {
      const a = pos.get(e.from)!, b = pos.get(e.to)!;
      const from: [number, number] = v ? [a[0] + nw / 2, a[1] + nh + BAR_GAP + BAR_H] : [a[0] + nw, a[1] + nh / 2];
      const to: [number, number] = v ? [b[0] + nw / 2, b[1]] : [b[0], b[1] + nh / 2];
      this.edgeLine.push({ from, to });
      svg.append(svgEl('line', { x1: from[0], y1: from[1], x2: to[0], y2: to[1], class: 'sim-edge' }));
    }
    for (const n of sc.nodes) {
      const [x, y] = pos.get(n.id)!;
      const r = svgEl('rect', { x, y, width: nw, height: nh, rx: 6, class: 'sim-node sim-ok' });
      const t = svgEl('text', { x: x + nw / 2, y: y + 19, class: 'sim-label', 'text-anchor': 'middle' });
      t.textContent = n.label;
      const u = svgEl('text', { x: x + nw / 2, y: y + 34, class: 'sim-sub', 'text-anchor': 'middle' });
      u.textContent = n.kind;
      const badge = svgEl('text', { x: x + nw / 2, y: y + 49, class: 'sim-badge', 'text-anchor': 'middle' });
      const qbg = svgEl('rect', { x, y: y + nh + BAR_GAP, width: nw, height: BAR_H, class: 'sim-qbg' });
      const q = svgEl('rect', { x, y: y + nh + BAR_GAP, width: 0, height: BAR_H, class: 'sim-q' });
      svg.append(r, t, u, badge, qbg, q);
      this.nodeRect.set(n.id, r); this.nodeBadge.set(n.id, badge); this.nodeQueue.set(n.id, q);
    }
    this.dotLayer = svgEl('g', { class: 'sim-dots', 'aria-hidden': 'true' });
    svg.append(this.dotLayer);
    const fig = el('div', 'sim-pic');
    fig.append(svg, el('p', 'sim-legend', 'Under each box: queue bar, filled in proportion to its queue limit. A box turns red and says "saturated" past 90 percent utilisation, amber and "busy" past 70 percent, and "crashed" when you crash it.'));
    const dl = el('dl', 'sim-readouts');
    for (const key of sc.readouts.includes('goodput') && !sc.readouts.includes('offered') ? ['offered', ...sc.readouts] : sc.readouts) {
      dl.append(el('dt', '', this.keyLabel(key)));
      const dd = el('dd', '', '-');
      dl.append(dd);
      this.readouts.set(key, dd);
    }
    const side = el('div', 'sim-side');
    side.append(dl, el('p', 'sim-legend', 'Every readout is a ' + READOUT_WINDOW_S + '-second mean over the same window. Offered load is what arrived; goodput is what completed successfully, shown as a share of offered and never above it.'));
    this.figure.append(fig, side);
  }

  readText(key: string, snap: SimSnapshot): string {
    const [name, node] = key.split(':');
    const m = this.meter.mean(key);
    if (!Number.isFinite(m)) return '-';
    switch (name) {
      case 'p50': case 'p95': case 'p99': return fmtMs(m);
      case 'offered': return fmtRate(m);
      case 'goodput': { const o = this.meter.mean('offered'); return fmtRate(m) + (o > 0 ? ' (' + Math.round((m / o) * 100) + '% of offered)' : ''); }
      case 'errors': case 'util': case 'hit': return fmtPct(m);
      case 'queue': case 'lag': return String(Math.round(m));
      case 'breaker': return snap.nodes[node]?.breakerState ?? 'closed';
      default: return fmtRate(m);
    }
  }

  /** Start in steady state: run the warm-up synchronously, filling the meter and the chart history. */
  warm(): void {
    const total = (this.sc.warmup_s || 0) * 1000;
    for (let done = 0; done < total; done += SAMPLE_MS) { this.sim.step(SAMPLE_MS); this.record(); }
    this.draw();
  }

  /** Step the model and sample the meter every SAMPLE_MS of simulated time. */
  advance(ms: number): void {
    this.sinceSample += ms;
    this.sim.step(ms);
    while (this.sinceSample >= SAMPLE_MS) { this.sinceSample -= SAMPLE_MS; this.record(); }
  }

  record(): void {
    const snap = this.sim.snapshot();
    this.meter.sample(snap);
    const t = snap.system.timeMs / 1000;
    this.hist.push({ t, p99: this.meter.mean('p99'), good: this.meter.mean('goodput'), offered: this.meter.mean('offered') });
    while (this.hist.length && this.hist[0].t < t - CHART_S) this.hist.shift();
  }

  frame(t: number): void {
    if (this.running && this.visible) {
      const dt = this.last ? Math.min(t - this.last, 100) : FRAME_MS;
      this.advance(dt);
      this.spawnDots(dt);
      this.draw();
    }
    this.last = t;
    requestAnimationFrame((tt) => this.frame(tt));
  }

  spawnDots(dt: number): void {
    const snap = this.sim.snapshot();
    this.sc.edges.forEach((e, i) => {
      const expected = ((snap.edgeFlow[e.id] ?? 0) * dt) / 1000 / 4; // one dot per four requests keeps the picture readable
      let n = Math.floor(expected);
      if (Math.random() < expected - n) n += 1; // the picture only: Math.random never feeds the engine
      for (let j = 0; j < n && this.dots.length < 400; j += 1) this.dots.push({ edge: i, t: 0 });
    });
    for (const d of this.dots) d.t += dt / 600;
    this.dots = this.dots.filter((d) => d.t < 1);
  }

  draw(): void {
    const snap = this.sim.snapshot();
    const crashed = new Set((this.sc.faults || []).filter((f) => this.sim.active.has(f.id)).map((f) => f.node));
    for (const n of this.sc.nodes) {
      const s = snap.nodes[n.id];
      if (!s) continue;
      const dead = crashed.has(n.id);
      const u = s.utilization;
      const cls = dead ? 'sim-down' : u >= 0.9 ? 'sim-hot' : u >= 0.7 ? 'sim-warm' : 'sim-ok';
      this.nodeRect.get(n.id)!.setAttribute('class', 'sim-node ' + cls);
      this.nodeBadge.get(n.id)!.textContent = dead ? 'crashed' : u >= 0.9 ? 'saturated' : u >= 0.7 ? 'busy' : '';
      const lim = n.config.queueLimit || 1;
      this.nodeQueue.get(n.id)!.setAttribute('width', String(Math.min(1, s.queued / lim) * (this.vertical ? VNODE_W : NODE_W)));
    }
    while (this.dotLayer.firstChild) this.dotLayer.removeChild(this.dotLayer.firstChild);
    if (!this.reduced) for (const d of this.dots) {
      const e = this.edgeLine[d.edge];
      this.dotLayer.append(svgEl('circle', { cx: e.from[0] + (e.to[0] - e.from[0]) * d.t, cy: e.from[1] + (e.to[1] - e.from[1]) * d.t, r: 3, class: 'sim-dot' }));
    }
    for (const [key, dd] of this.readouts) dd.textContent = this.readText(key, snap);
    this.chart();
  }

  chart(): void {
    const c = this.canvas, ctx = c.getContext('2d');
    if (!ctx) return;
    const cw = Math.max(300, Math.round(c.clientWidth || 640));
    if (c.width !== cw) { c.width = cw; c.height = Math.max(150, Math.round(cw * 0.28)); } // draw at the displayed size so the text stays readable on a phone
    const W = c.width, H = c.height, L = 58, R = 56, T = 10, B = 22;
    const css = getComputedStyle(this.root);
    const tok = (name: string, fb: string): string => css.getPropertyValue(name).trim() || fb;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = tok('--sim-bg', '#fff');
    ctx.fillRect(0, 0, W, H);
    const h = this.hist;
    if (h.length < 2) return;
    const t1 = h[h.length - 1].t, span = Math.min(CHART_S, Math.max(10, t1 - h[0].t)), t0 = t1 - span;
    const maxP = Math.max(100, ...h.map((p) => p.p99)) * 1.1;
    const maxG = Math.max(10, ...h.map((p) => Math.max(p.good, p.offered))) * 1.1;
    const x = (t: number): number => L + ((t - t0) / span) * (W - L - R);
    const yP = (v: number): number => T + (1 - v / maxP) * (H - T - B);
    const yG = (v: number): number => T + (1 - v / maxG) * (H - T - B);
    ctx.strokeStyle = tok('--sim-grid', '#bbb');
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(L, T); ctx.lineTo(L, H - B); ctx.lineTo(W - R, H - B); ctx.moveTo(W - R, T); ctx.lineTo(W - R, H - B); ctx.stroke();
    ctx.fillStyle = tok('--sim-fg', '#222');
    ctx.font = '12px system-ui, sans-serif';
    ctx.textAlign = 'right'; ctx.fillText(Math.round(maxP / 1.1) + ' ms', L - 5, T + 10);
    ctx.textAlign = 'left'; ctx.fillText(Math.round(maxG / 1.1) + ' /s', W - R + 5, T + 10);
    ctx.textAlign = 'center'; ctx.fillText('last ' + Math.round(span) + ' s', (L + W - R) / 2, H - 5);
    const line = (colour: string, dash: number[], width: number, f: (p: Pt) => number, y: (v: number) => number): void => {
      ctx.strokeStyle = colour; ctx.lineWidth = width; ctx.setLineDash(dash);
      ctx.beginPath(); h.forEach((p, i) => (i ? ctx.lineTo(x(p.t), y(f(p))) : ctx.moveTo(x(p.t), y(f(p))))); ctx.stroke();
    };
    line(tok('--sim-offered', '#888'), [2, 3], 1.5, (p) => p.offered, yG);
    line(tok('--sim-good', '#1f5fa8'), [7, 4], 2, (p) => p.good, yG);
    line(tok('--sim-p99', '#a3321c'), [], 2, (p) => p.p99, yP);
    ctx.setLineDash([]);
  }
}

async function boot(): Promise<void> {
  for (const host of Array.from(document.querySelectorAll<HTMLElement>('[data-scenario]'))) {
    const url = host.dataset.scenario!;
    try {
      const res = await fetch(url, { credentials: 'omit' });
      if (!res.ok) throw new Error('scenario ' + url + ' answered ' + res.status);
      const sc = (await res.json()) as Scenario;
      host.classList.add('sim-ready');
      new Block(host, sc);
      console.log('[sim] block ready: ' + sc.id);
    } catch (err) {
      host.textContent = 'The simulation could not start: ' + String(err);
      console.error('[sim] ' + String(err));
    }
  }
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => { void boot(); });
else void boot();
