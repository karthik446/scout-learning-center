#!/usr/bin/env node
// Golden runner. For each scenario (content/scenarios/<id>.json): a "defaults" row (every knob at its default, nothing
// crashed) plus one row per assertion, each run on the built engine (assets/sim/engine.js) for the scenario's seed:
// warm-up, faults, settle, then one sample a second over the window. Prints the readouts and the verdicts.
//   node tools/sim/golden.mjs [--write | --check] [id ...]     (no ids: every scenario)
// --write  writes tools/sim/golden/<id>.json     --check  exits 1 when a row differs from the committed file or an assertion fails
import { readFileSync, writeFileSync, readdirSync, existsSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { loadEngine, ROOT } from './load.mjs';

const SCEN = join(ROOT, 'content', 'scenarios');
const GOLD = join(ROOT, 'tools', 'sim', 'golden');
const args = process.argv.slice(2);
const write = args.includes('--write'), check = args.includes('--check');
let ids = args.filter((a) => !a.startsWith('--'));
if (!ids.length) ids = readdirSync(SCEN).filter((f) => f.endsWith('.json')).map((f) => f.slice(0, -5)).sort();

const { runWindow, runAssertion, keysOf } = await loadEngine();
const round = (v) => (typeof v === 'number' ? Math.round(v * 10000) / 10000 : v);
const roundObj = (o) => Object.fromEntries(Object.entries(o).map(([k, v]) => [k, round(v)]));
const vendorHash = () => {
  const m = readFileSync(join(ROOT, 'vendor', 'breakscale', 'UPSTREAM.txt'), 'utf8').match(/^([0-9a-f]{64})  engine\.ts$/gm);
  return m[m.length - 1].split('  ')[0];
};

function golden(sc) {
  const rows = [];
  const defaults = Object.fromEntries(sc.knobs.map((k) => [k.id, k.default]));
  const { metrics } = runWindow(sc, defaults, [], 0, sc.window_s, keysOf(sc));
  rows.push({ assertion: 'defaults', knobs: defaults, faults: [], metrics: roundObj(metrics), pass: true });
  for (const a of sc.assertions) {
    const r = runAssertion(sc, a);
    rows.push({ assertion: a.id, knobs: a.knobs, faults: r.faults, metric: a.metric, op: a.op, value: a.value, got: round(r.got), metrics: roundObj(r.metrics), pass: r.pass });
  }
  return {
    schema_version: 'learning-center-sim-golden:1', id: sc.id, seed: sc.seed, commit: 'd2c876e0', engine_ts_sha256: vendorHash(),
    scenario_sha256: createHash('sha256').update(JSON.stringify(sc)).digest('hex'), rows,
  };
}

let bad = 0;
for (const id of ids) {
  const sc = JSON.parse(readFileSync(join(SCEN, id + '.json'), 'utf8'));
  const g = golden(sc);
  console.log(`\n${id}  seed ${sc.seed}  warm-up ${sc.warmup_s} s  window ${sc.window_s} s`);
  for (const r of g.rows) {
    const shown = sc.readouts.concat(r.metric && !sc.readouts.includes(r.metric) ? [r.metric] : []).map((k) => `${k}=${r.metrics[k]}`).join('  ');
    console.log(`  ${r.pass ? 'pass' : 'FAIL'}  ${r.assertion}  ${JSON.stringify(r.knobs)}${r.faults.length ? ' faults ' + r.faults : ''}\n        ${r.metric ? `${r.metric} ${r.op} ${JSON.stringify(r.value)}: got ${r.got}\n        ` : ''}${shown}`);
    if (!r.pass) bad += 1;
  }
  const file = join(GOLD, id + '.json');
  const text = JSON.stringify(g, null, 1) + '\n';
  if (write) { mkdirSync(GOLD, { recursive: true }); writeFileSync(file, text); console.log('  wrote', file); }
  if (check) {
    if (!existsSync(file)) { console.error(`  DRIFT ${id}: no committed golden file`); bad += 1; }
    else if (readFileSync(file, 'utf8') !== text) {
      const old = JSON.parse(readFileSync(file, 'utf8'));
      for (const [i, r] of g.rows.entries()) if (JSON.stringify(r) !== JSON.stringify(old.rows[i])) console.error(`  DRIFT ${id}/${r.assertion}: committed ${JSON.stringify(old.rows[i]?.metrics)} now ${JSON.stringify(r.metrics)}`);
      if (g.scenario_sha256 !== old.scenario_sha256) console.error(`  DRIFT ${id}: the scenario file changed since the golden file was written`);
      if (g.engine_ts_sha256 !== old.engine_ts_sha256) console.error(`  DRIFT ${id}: the vendored engine changed`);
      bad += 1;
    }
  }
}
if (bad) { console.error(`\n${bad} problem(s)`); process.exit(1); }
