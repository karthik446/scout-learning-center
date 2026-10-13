// Closed-form checks of the vendored engine (plan 7.3): textbook queues run on the built engine, 4 seeds each,
// compared with the formulas. Run: node --test tools/sim/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { loadEngine } from './load.mjs';

const { Sim, Meter } = await loadEngine();

const SEEDS = [1, 2, 3, 4];
const WARM_S = 30, WINDOW_S = 150;

const base = { capacity: 1, serviceMs: 0, serviceCv: 0, queueLimit: 0, hitRate: 0, errorRate: 0, timeoutMs: 0, retries: 0, rps: 0 };
/** client -> one service node with `slots` parallel slots, mean service time 1000/mu ms, coefficient of variation cv. */
function queue({ lambda, mu, slots = 1, cv = 1, seed }) {
  return {
    schema_version: 'learning-center-sim:1', id: 'test', title: 'test', seed, warmup_s: 0, window_s: WINDOW_S, scale_note: null,
    nodes: [
      { id: 'client', kind: 'client', label: 'c', x: 0, y: 0, config: { ...base, rps: lambda, timeoutMs: 0 } },
      { id: 'svc', kind: 'service', label: 's', x: 1, y: 0, config: { ...base, capacity: slots, instances: 1, serviceMs: 1000 / mu, serviceCv: cv, queueLimit: 1000000 } },
    ],
    edges: [{ id: 'e', from: 'client', to: 'svc', weight: 1 }], knobs: [], readouts: [], assertions: [],
  };
}

/** Mean over WINDOW_S one-second samples after WARM_S, averaged over the seeds. */
function measure(shape) {
  const keys = ['p50', 'p99', 'util:svc', 'queue:svc', 'offered'];
  const per = SEEDS.map((seed) => {
    const sim = new Sim(queue({ ...shape, seed }));
    sim.step(WARM_S * 1000);
    const m = new Meter(keys.concat(['inflight']), WINDOW_S + 1);
    const inflight = [];
    for (let s = 0; s < WINDOW_S; s += 1) { sim.step(1000); const snap = sim.snapshot(); m.sample(snap); inflight.push(snap.nodes.svc.inFlight + snap.nodes.svc.queued); }
    return { p50: m.mean('p50'), p99: m.mean('p99'), util: m.mean('util:svc'), lq: m.mean('queue:svc'), offered: m.mean('offered'), l: inflight.reduce((a, b) => a + b, 0) / inflight.length };
  });
  const avg = (k) => per.reduce((a, r) => a + r[k], 0) / per.length;
  return { p50: avg('p50'), p99: avg('p99'), util: avg('util'), lq: avg('lq'), offered: avg('offered'), l: avg('l'), per };
}
const within = (got, want, rel, what) => assert.ok(Math.abs(got - want) <= rel * want, `${what}: got ${got.toFixed(3)}, want ${want.toFixed(3)} within ${rel * 100}%`);

// M/M/1: sojourn time is exponential with rate mu - lambda.
// p99 comes from a trailing 5 s window (engine LATENCY_WINDOW_MS) of strongly autocorrelated completions, so the mean of the
// per-second p99 estimates sits below the stationary p99, more so the busier the queue: measured -4% at rho 0.5 and -20% at
// rho 0.8 over 8 seeds x 600 s (with the cap patch, every completion in the window is sorted; without it -35%). The
// tolerances below state that bias; p50, utilisation and queue depth carry no such bias.
for (const [lambda, mu, p99Tol] of [[100, 200, 0.10], [160, 200, 0.25]]) {
  test(`M/M/1 lambda ${lambda} mu ${mu}`, () => {
    const rho = lambda / mu, rate = (mu - lambda) / 1000; // per ms
    const r = measure({ lambda, mu });
    assert.ok(Math.abs(r.util - rho) <= 0.03, `utilisation ${r.util} vs ${rho}`);
    within(r.p50, Math.log(2) / rate, 0.10, 'p50');
    within(r.p99, Math.log(100) / rate, p99Tol, 'p99 (5 s window estimator, patched cap)');
    within(r.lq, (rho * rho) / (1 - rho), 0.30, 'queued (Lq)');
    // Little's law: customers in the system = arrival rate x mean sojourn (1 / (mu - lambda)).
    within(r.l, r.offered * (1 / (mu - lambda)), 0.15, "Little's law, L = lambda W");
  });
}

/** Erlang C for c servers, offered load a = lambda / mu. */
function erlangC(c, a) {
  let sum = 0, term = 1;
  for (let k = 0; k < c; k += 1) { if (k > 0) term *= a / k; sum += term; }
  const top = (term * a / c) * (c / (c - a));
  return top / (sum + top);
}
// M/M/4: waiting time is 0 with probability 1 - C, else exponential with rate c mu - lambda.
test('M/M/4 lambda 160 mu 50 per slot', () => {
  const c = 4, mu = 50, lambda = 160, a = lambda / mu, rho = a / c;
  const C = erlangC(c, a);
  const r = measure({ lambda, mu, slots: c });
  assert.ok(Math.abs(r.util - rho) <= 0.03, `utilisation ${r.util} vs ${rho}`);
  within(C, 0.596, 0.01, 'Erlang C itself (the figure of plan 7.0)');
  const lq = (C * rho) / (1 - rho);
  within(r.lq, lq, 0.30, 'queued (Lq)');
  // sojourn tail: T = Wq + S, S ~ Exp(mu), Wq = 0 w.p. 1 - C else Exp(theta); hypoexponential for the second term.
  const th = (c * mu - lambda), m = mu; // per second
  const tail = (t) => (1 - C) * Math.exp(-m * t) + C * ((m * Math.exp(-th * t) - th * Math.exp(-m * t)) / (m - th));
  const q = (p) => { let lo = 0, hi = 5; for (let i = 0; i < 80; i += 1) { const mid = (lo + hi) / 2; if (tail(mid) > 1 - p) lo = mid; else hi = mid; } return ((lo + hi) / 2) * 1000; };
  within(r.p50, q(0.5), 0.10, 'p50');
  within(r.p99, q(0.99), 0.20, 'p99');
});

// Kingman / Pollaczek-Khinchine for M/G/1 (exact for Poisson arrivals): Wq = rho / (1 - rho) x (1 + cs^2) / 2 x E[S], Lq = lambda Wq.
test('Kingman, M/G/1 with service cv 0.5 at rho 0.8', () => {
  const lambda = 160, mu = 200, cv = 0.5, rho = lambda / mu;
  const wq = (rho / (1 - rho)) * ((1 + cv * cv) / 2) * (1 / mu); // seconds
  const r = measure({ lambda, mu, cv });
  assert.ok(Math.abs(r.util - rho) <= 0.03, `utilisation ${r.util} vs ${rho}`);
  within(r.lq, lambda * wq, 0.30, 'queued (Lq = lambda Wq)');
  // and the whole point of Kingman: lower variability than M/M/1 means a shorter queue
  const mm1 = measure({ lambda, mu, cv: 1 });
  assert.ok(r.lq < mm1.lq, `cv 0.5 queue ${r.lq} should be below cv 1 queue ${mm1.lq}`);
});
