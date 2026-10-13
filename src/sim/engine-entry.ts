// Entry of the engine-only bundle (assets/sim/engine.js): the model and the shared scenario runner, no DOM.
// The headless golden runner and the node tests import this file, so they run the same code the page runs.
export * from './core';
