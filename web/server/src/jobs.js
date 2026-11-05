/**
 * Runs the Python batch jobs (src/web_export.py): model scoring, data review, reset.
 * One job at a time; re-scoring after writes is debounced.
 */
import { spawn } from 'node:child_process';
import { PROJECT_ROOT, PYTHON } from './config.js';

const state = { running: null, queued: false, last: null };
let timer = null;

export const status = () => ({ running: state.running, queued: state.queued, last: state.last });

export function runJob(job) {
  if (state.running) return Promise.reject(new Error(`Job '${state.running}' is already running.`));
  state.running = job;
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const child = spawn(PYTHON, ['-W', 'ignore', '-m', 'src.web_export', job], { cwd: PROJECT_ROOT });
    let out = '';
    let err = '';
    child.stdout.on('data', (d) => { out += d; });
    child.stderr.on('data', (d) => { err += d; });
    child.on('error', (e) => finish(false, `Could not start Python (${PYTHON}): ${e.message}`));
    child.on('close', (code) => finish(code === 0, code === 0 ? out.trim().split('\n').at(-1) : err.slice(-1500)));

    function finish(ok, output) {
      if (state.running !== job) return;
      state.running = null;
      state.last = { job, ok, output, finished_at: new Date().toISOString(), seconds: (Date.now() - started) / 1000 };
      if (state.queued) { state.queued = false; scheduleRescore(0); }
      ok ? resolve(state.last) : reject(new Error(output || `Job '${job}' failed`));
    }
  });
}

/** Re-score open deals shortly after a write (coalesces bursts of edits). */
export function scheduleRescore(delayMs = 1500) {
  if (process.env.CRM_DISABLE_RESCORE === '1') return; // tests run against a copy of the DB
  if (state.running) { state.queued = true; return; }
  clearTimeout(timer);
  timer = setTimeout(() => runJob('predictions').catch((e) => console.error('[rescore]', e.message)), delayMs);
}
