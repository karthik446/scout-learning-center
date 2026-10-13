# Local patches to the vendored Breakscale engine

Upstream: https://github.com/xevrion/breakscale, commit d2c876e0 (MIT, see LICENSE). Every other file is byte-identical to upstream (hashes in UPSTREAM.txt). A re-pin is a copy, then this patch is re-applied (or dropped) and the hashes regenerated.

## 1. PERCENTILE_SAMPLE_CAP 512 -> 4096 (exact p99)

- File: `engine.ts`, line 48.
- Before: `const PERCENTILE_SAMPLE_CAP = 512;`
- After:  `const PERCENTILE_SAMPLE_CAP = 4096;`
- sha256 of `engine.ts` before: `1074807a8d0007e09260060afeac55bcce6682de48276df99f07dbd2aca1fb08`
- sha256 of `engine.ts` after:  `1c812d4a253c9c095c41f0d88c0ec97434bfdfc189279065d9ca9beca250666f`
- Why: percentiles come from the trailing 5 s window of a 4096-slot ring (`LATENCY_RING`), but at most `PERCENTILE_SAMPLE_CAP` samples were sorted, strided over the whole ring. At 160 requests a second the window holds about 800 completions and the sort saw about 100, so the 99th percentile was nearly the sample maximum and read 15 to 30 percent low against the M/M/1 closed form (plan 7.0). With the cap equal to the ring size every completion in the window is sorted, so quoted p99 values are exact for the window. Operator decision 2026-10-13. Cost: one sort of up to 4096 floats per snapshot (cached per tick).
- Applies to the browser block and the headless runner alike (one engine, one build), so what a learner sees is what the golden run quoted.
