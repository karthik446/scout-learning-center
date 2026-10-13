// Load the built engine-only module (assets/sim/engine.js) into node whatever the node version's module detection:
// the file is an ES module with a .js extension and no package.json beside it, so it is imported through a data: URL.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

export const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
export async function loadEngine() {
  const src = readFileSync(join(ROOT, 'assets', 'sim', 'engine.js'), 'utf8');
  return import('data:text/javascript;base64,' + Buffer.from(src).toString('base64'));
}
