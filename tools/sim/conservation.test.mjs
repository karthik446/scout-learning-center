// Conservation and bounds over every committed scenario (plan 7.3 item 5), our own cases on the built engine:
// requests are not created or lost, failure reasons add up, utilisation stays in [0, 1], nothing is NaN or infinite,
// the goodput we show never exceeds offered. Each scenario runs at its defaults, at the extreme of every knob, and with every fault on.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { loadEngine, ROOT } from './load.mjs';

const { Sim, Meter, keysOf } = await loadEngine();
const dir = join(ROOT, 'content', 'scenarios');
const scenarios = readdirSync(dir).filter((f) => f.endsWith('.json')).sort().map((f) => JSON.parse(readFileSync(join(dir, f), 'utf8')));

function finite(o, path, out) {
  if (typeof o === 'number') { if (!Number.isFinite(o)) out.push(path + ' = ' + o); }
  else if (Array.isArray(o)) o.forEach((v, i) => finite(v, path + '[' + i + ']', out));
  else if (o && typeof o === 'object') for (const [k, v] of Object.entries(o)) finite(v, path + '.' + k, out);
}

function settings(sc) {
  const out = [{ name: 'defaults', knobs: {}, faults: [] }];
  for (const k of sc.knobs) for (const v of [k.min, k.max]) out.push({ name: `${k.id}=${v}`, knobs: { [k.id]: v }, faults: [] });
  if ((sc.faults || []).length) out.push({ name: 'all faults', knobs: {}, faults: sc.faults.map((f) => f.id) });
  return out;
}

for (const sc of scenarios) for (const s of settings(sc)) {
  test(`${sc.id}: ${s.name}`, () => {
    const sim = new Sim(sc);
    for (const [id, v] of Object.entries(s.knobs)) sim.setKnob(id, v);
    sim.step(sc.warmup_s * 1000);
    for (const f of s.faults) sim.setFault(f, true);
    const meter = new Meter(keysOf(sc).concat([]), 31);
    for (let t = 0; t < 40; t += 1) {
      sim.step(1000);
      const snap = sim.snapshot();
      const bad = []; finite({ system: snap.system, nodes: snap.nodes, edgeFlow: snap.edgeFlow }, 'snap', bad);
      assert.deepEqual(bad, [], 'NaN or infinity in the snapshot');
      for (const [id, n] of Object.entries(snap.nodes)) {
        assert.ok(n.utilization >= 0 && n.utilization <= 1 + 1e-9, `utilisation of ${id} is ${n.utilization}`);
        assert.ok(n.queued >= 0 && n.inFlight >= 0, `negative depth at ${id}`);
      }
      const reasons = Object.values(snap.failuresByReason).reduce((a, b) => a + b, 0);
      assert.equal(reasons, snap.system.totalFailed, 'failures by reason must sum to the failure total');
      const clients = sc.nodes.filter((n) => n.kind === 'client').map((n) => snap.nodes[n.id]);
      const settled = clients.reduce((a, n) => a + n.totalCompleted + n.totalFailed, 0);
      assert.ok(settled <= snap.system.totalRequests, `settled ${settled} exceeds requests made ${snap.system.totalRequests}`);
      assert.ok(snap.system.errorRate >= 0 && snap.system.errorRate <= 1, 'error rate outside [0, 1]');
      meter.sample(snap);
    }
    assert.ok(meter.mean('goodput') <= meter.mean('offered') + 1e-9, 'goodput shown must not exceed offered');
  });
}
