import { randomInt } from 'node:crypto';
import { existsSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import express from 'express';

import * as A from './analytics.js';
import { OPEN_STAGES, WEB_DIR } from './config.js';
import * as db from './db.js';
import { runJob, scheduleRescore, status } from './jobs.js';
import { cleanOpportunity, validateAccount, validateOpportunity } from './validation.js';

export const router = express.Router();

class HttpError extends Error {
  constructor(status, message, errors) { super(message); this.status = status; this.errors = errors; }
}
const list = (v) => (v ? String(v).split(',').map((s) => s.trim()).filter(Boolean) : []);
const nowIso = () => new Date().toISOString().slice(0, 19);
const contains = (q) => (val) => val != null && String(val).toLowerCase().includes(q);

function ctx() {
  const l = db.lookups();
  return { agents: new Set(l.agents.map((a) => a.sales_agent)), products: new Set(l.products.map((p) => p.product)),
           accounts: new Set(l.accounts) };
}

function newId() {
  const abc = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
  const existing = new Set(db.conn().prepare('SELECT opportunity_id FROM opportunities').all().map((r) => r.opportunity_id));
  for (;;) {
    const id = Array.from({ length: 8 }, () => abc[randomInt(abc.length)]).join('');
    if (!existing.has(id)) return id;
  }
}

// ---------------------------------------------------------------------------
// Meta / lookups / search
// ---------------------------------------------------------------------------
router.get('/meta', (req, res) => {
  const { master, snapshot } = db.loadMaster();
  const entries = db.conn().prepare(`SELECT
      (SELECT COUNT(*) FROM opportunities WHERE source='user' OR updated_at IS NOT NULL) AS opps,
      (SELECT COUNT(*) FROM accounts WHERE source='user') AS accounts`).get();
  res.json({ ...db.meta(), snapshot, opportunities: master.length, user_entries: entries, jobs: status() });
});

router.get('/lookups', (req, res) => res.json(db.lookups()));

router.get('/search', (req, res) => {
  const q = String(req.query.q || '').trim().toLowerCase();
  if (q.length < 2) return res.json({ opportunities: [], accounts: [], reps: [] });
  const { master } = db.loadMaster();
  const has = contains(q);
  const l = db.lookups();
  res.json({
    opportunities: master.filter((r) => has(r.opportunity_id) || has(r.account) || has(r.product))
      .slice(0, 6).map(({ opportunity_id, account, product, deal_stage, sales_agent }) =>
        ({ opportunity_id, account, product, deal_stage, sales_agent })),
    accounts: l.accounts.filter(has).slice(0, 5),
    reps: l.agents.filter((a) => has(a.sales_agent)).slice(0, 5),
  });
});

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------
router.get('/dashboard', (req, res) => {
  const { master, snapshot } = db.loadMaster();
  const offices = list(req.query.offices);
  const products = list(req.query.products);
  const { from, to } = req.query;
  const rows = master.filter((r) =>
    (!offices.length || offices.includes(r.regional_office))
    && (!products.length || products.includes(r.product))
    && (r.is_open || ((!from || r.close_date >= from) && (!to || r.close_date <= to))));

  const closedDates = master.filter((r) => r.close_date).map((r) => r.close_date).sort();
  const pick = (r) => ({ opportunity_id: r.opportunity_id, account: r.account, product: r.product,
                         deal_stage: r.deal_stage, sales_agent: r.sales_agent, est_open_value: r.est_open_value,
                         win_probability: r.win_probability });
  res.json({
    snapshot, total: master.length, filtered: rows.length,
    date_bounds: { min: closedDates[0], max: closedDates.at(-1) },
    kpis: A.kpis(rows),
    monthly: A.monthly(rows),
    stages: A.stages(rows),
    by_product: A.summariseBy(rows, (r) => r.product),
    by_office: A.summariseBy(rows, (r) => r.regional_office).sort((a, b) => b.win_rate - a.win_rate),
    top_reps: A.summariseBy(rows, (r) => r.sales_agent).slice(0, 10),
    by_sector: A.summariseBy(rows.filter((r) => r.account_known), (r) => r.sector),
    top_open: rows.filter((r) => r.is_open).sort((a, b) => (b.est_open_value ?? 0) - (a.est_open_value ?? 0))
      .slice(0, 8).map(pick),
    recent: rows.filter((r) => r.source === 'user' || r.updated_at)
      .sort((a, b) => String(b.updated_at || b.created_at).localeCompare(String(a.updated_at || a.created_at)))
      .slice(0, 6).map((r) => ({ ...pick(r), at: r.updated_at || r.created_at, kind: r.updated_at ? 'updated' : 'created' })),
  });
});

// ---------------------------------------------------------------------------
// Opportunities
// ---------------------------------------------------------------------------
const OPP_SORT = new Set(['opportunity_id', 'deal_stage', 'account', 'product', 'sales_agent', 'engage_date',
  'close_date', 'close_value', 'est_open_value', 'win_probability', 'regional_office']);

router.get('/opportunities', (req, res) => {
  const { master } = db.loadMaster();
  const q = String(req.query.q || '').trim().toLowerCase();
  const stagesQ = list(req.query.stages);
  const { rep, product, office, source } = req.query;
  let rows = master.filter((r) => (!stagesQ.length || stagesQ.includes(r.deal_stage))
    && (!rep || r.sales_agent === rep) && (!product || r.product === product)
    && (!office || r.regional_office === office) && (!source || r.source === source));
  if (q) {
    const has = contains(q);
    rows = rows.filter((r) => has(r.opportunity_id) || has(r.account) || has(r.sales_agent) || has(r.product)
      || has(r.sector));
  }
  const sort = OPP_SORT.has(req.query.sort) ? req.query.sort : null;
  const dir = req.query.dir === 'asc' ? 1 : -1;
  rows = [...rows].sort(sort
    ? (a, b) => (a[sort] == null) - (b[sort] == null) || (a[sort] > b[sort] ? dir : a[sort] < b[sort] ? -dir : 0)
    : (a, b) => (b.is_open - a.is_open) || String(b.engage_date ?? '').localeCompare(String(a.engage_date ?? '')));
  const k = A.kpis(rows);
  const pageSize = req.query.pageSize === 'all' ? Math.max(rows.length, 1) : Math.min(Number(req.query.pageSize) || 25, 200);
  const page = Math.max(Number(req.query.page) || 1, 1);
  res.json({ total: rows.length, page, pageSize, summary: k, rows: rows.slice((page - 1) * pageSize, page * pageSize) });
});

router.get('/opportunities/:id', (req, res) => {
  const row = db.loadMaster().master.find((r) => r.opportunity_id === req.params.id);
  if (!row) throw new HttpError(404, 'Opportunity not found');
  res.json(row);
});

router.post('/opportunities', (req, res) => {
  const rec = req.body || {};
  const errors = validateOpportunity(rec, ctx());
  if (errors.length) throw new HttpError(422, 'Validation failed', errors);
  const row = { opportunity_id: newId(), ...cleanOpportunity(rec), source: 'user', created_at: nowIso() };
  db.tx((d) => {
    d.prepare(`INSERT INTO opportunities (${Object.keys(row).join(', ')}) VALUES (${Object.keys(row).map(() => '?').join(', ')})`)
      .run(...Object.values(row));
    db.bump();
  });
  scheduleRescore();
  res.status(201).json(row);
});

router.patch('/opportunities/:id', (req, res) => {
  const cur = db.conn().prepare('SELECT * FROM opportunities WHERE opportunity_id = ?').get(req.params.id);
  if (!cur) throw new HttpError(404, 'Opportunity not found');
  if (!OPEN_STAGES.includes(cur.deal_stage)) throw new HttpError(409, 'Only open deals can be updated', ['This deal is already closed.']);
  const rec = { ...cur, ...req.body };
  const errors = validateOpportunity(rec, ctx());
  if (errors.length) throw new HttpError(422, 'Validation failed', errors);
  const row = { ...cleanOpportunity(rec), updated_at: nowIso() };
  db.tx((d) => {
    d.prepare(`UPDATE opportunities SET ${Object.keys(row).map((k) => `${k} = ?`).join(', ')} WHERE opportunity_id = ?`)
      .run(...Object.values(row), req.params.id);
    db.bump();
  });
  scheduleRescore();
  res.json({ opportunity_id: req.params.id, ...row });
});

router.delete('/opportunities/:id', (req, res) => {
  const n = db.tx((d) => {
    const r = d.prepare("DELETE FROM opportunities WHERE opportunity_id = ? AND source = 'user'").run(req.params.id);
    if (r.changes) db.bump();
    return r.changes;
  });
  if (!n) throw new HttpError(403, 'Only entries created in this app can be deleted.');
  scheduleRescore();
  res.status(204).end();
});

router.get('/pipeline', (req, res) => {
  const { master } = db.loadMaster();
  const rep = req.query.rep;
  const rows = master.filter((r) => !rep || r.sales_agent === rep);
  const byStage = (s, n, sortKey) => rows.filter((r) => r.deal_stage === s)
    .sort((a, b) => String(b[sortKey] ?? '').localeCompare(String(a[sortKey] ?? ''))).slice(0, n);
  res.json({
    rep, totals: Object.fromEntries(A.stages(rows).map((s) => [s.stage, s])),
    columns: { Prospecting: byStage('Prospecting', 60, 'created_at'), Engaging: byStage('Engaging', 60, 'engage_date'),
               Won: byStage('Won', 12, 'close_date'), Lost: byStage('Lost', 12, 'close_date') },
  });
});

// ---------------------------------------------------------------------------
// Accounts
// ---------------------------------------------------------------------------
router.get('/accounts', (req, res) => {
  const { master } = db.loadMaster();
  const stats = new Map(A.summariseBy(master.filter((r) => r.account_known), (r) => r.account).map((s) => [s.key, s]));
  const accounts = db.conn().prepare('SELECT * FROM accounts ORDER BY account').all().map((a) => {
    const s = stats.get(a.account) || {};
    return { ...a, opportunities: s.opportunities ?? 0, open: s.open ?? 0, won: s.won ?? 0, lost: s.lost ?? 0,
             win_rate: s.win_rate ?? null, won_revenue: s.won_revenue ?? 0,
             open_pipeline_est_value: s.open_pipeline_est_value ?? 0 };
  });
  res.json({ accounts, unassigned: master.filter((r) => !r.account_known).length });
});

router.get('/accounts/:name', (req, res) => {
  const acc = db.conn().prepare('SELECT * FROM accounts WHERE account = ?').get(req.params.name);
  if (!acc) throw new HttpError(404, 'Account not found');
  const deals = db.loadMaster().master.filter((r) => r.account === acc.account)
    .sort((a, b) => String(b.engage_date ?? '').localeCompare(String(a.engage_date ?? '')));
  const products = A.summariseBy(deals, (r) => r.product).map((p) => ({ product: p.key, won: p.won, lost: p.lost, open: p.open }));
  res.json({ account: acc, kpis: A.kpis(deals), deals, products, monthly: A.monthly(deals) });
});

router.post('/accounts', (req, res) => {
  const rec = req.body || {};
  const existing = new Set(db.lookups().accounts);
  const errors = validateAccount(rec, existing);
  if (errors.length) throw new HttpError(422, 'Validation failed', errors);
  const row = {
    account: String(rec.account).trim(), sector: String(rec.sector).trim().toLowerCase(),
    year_established: rec.year_established ?? null, revenue: rec.revenue ?? null, employees: rec.employees ?? null,
    office_location: rec.office_location || null, subsidiary_of: rec.subsidiary_of || null,
    source: 'user', created_at: nowIso(),
  };
  db.tx((d) => {
    d.prepare(`INSERT INTO accounts (${Object.keys(row).join(', ')}) VALUES (${Object.keys(row).map(() => '?').join(', ')})`)
      .run(...Object.values(row));
    db.bump();
  });
  res.status(201).json(row);
});

router.delete('/accounts/:name', (req, res) => {
  db.tx((d) => {
    const used = d.prepare('SELECT COUNT(*) AS n FROM opportunities WHERE account = ?').get(req.params.name).n;
    if (used) throw new HttpError(409, 'Account in use', [`'${req.params.name}' still has ${used} opportunities. Delete those first.`]);
    const r = d.prepare("DELETE FROM accounts WHERE account = ? AND source = 'user'").run(req.params.name);
    if (!r.changes) throw new HttpError(403, 'Only accounts created in this app can be deleted.');
    db.bump();
  });
  res.status(204).end();
});

// ---------------------------------------------------------------------------
// Team
// ---------------------------------------------------------------------------
router.get('/team', (req, res) => {
  const { master } = db.loadMaster();
  const rows = req.query.office ? master.filter((r) => r.regional_office === req.query.office) : master;
  res.json({ reps: A.repPerformance(rows), kpis: A.kpis(rows) });
});

router.get('/team/:agent', (req, res) => {
  const rows = db.loadMaster().master.filter((r) => r.sales_agent === req.params.agent);
  if (!rows.length) throw new HttpError(404, 'No deals for this rep');
  res.json({ agent: req.params.agent, manager: rows[0].manager, regional_office: rows[0].regional_office,
             kpis: A.kpis(rows), monthly: A.monthly(rows),
             products: A.summariseBy(rows, (r) => r.product) });
});

// ---------------------------------------------------------------------------
// User entries
// ---------------------------------------------------------------------------
router.get('/entries', (req, res) => {
  const d = db.conn();
  res.json({
    opportunities: d.prepare(`SELECT * FROM opportunities WHERE source='user' OR updated_at IS NOT NULL
                              ORDER BY COALESCE(updated_at, created_at) DESC`).all(),
    accounts: d.prepare("SELECT * FROM accounts WHERE source='user' ORDER BY created_at DESC").all(),
  });
});

// ---------------------------------------------------------------------------
// Model + data review (produced by the Python jobs)
// ---------------------------------------------------------------------------
const jsonCache = new Map();
function readWebJson(name) {
  const file = path.join(WEB_DIR, name);
  if (!existsSync(file)) throw new HttpError(404, `${name} has not been generated yet. Run the 'review' job.`);
  const mtime = statSync(file).mtimeMs;
  const hit = jsonCache.get(name);
  if (hit && hit.mtime === mtime) return hit.data;
  const data = JSON.parse(readFileSync(file, 'utf-8'));
  jsonCache.set(name, { mtime, data });
  return data;
}

router.get('/model', (req, res) => res.json(readWebJson('model.json')));
router.get('/review', (req, res) => res.json(readWebJson('review.json')));

const REVIEW_TABLES = { raw_joined: 'raw_joined.json', clean: 'clean.json', sales_pipeline: 'raw_sales_pipeline.json',
  accounts: 'raw_accounts.json', products: 'raw_products.json', sales_teams: 'raw_sales_teams.json',
  data_dictionary: 'raw_data_dictionary.json' };

router.get('/review/table/:name', (req, res) => {
  const file = REVIEW_TABLES[req.params.name];
  if (!file) throw new HttpError(404, 'Unknown table');
  const { columns, rows } = readWebJson(file);
  const q = String(req.query.q || '').trim().toLowerCase();
  const filtered = q ? rows.filter((r) => columns.some((c) => r[c] != null && String(r[c]).toLowerCase().includes(q))) : rows;
  const pageSize = Math.min(Number(req.query.pageSize) || 50, 500);
  const page = Math.max(Number(req.query.page) || 1, 1);
  res.json({ columns, total: filtered.length, all: rows.length, page, pageSize,
             rows: filtered.slice((page - 1) * pageSize, page * pageSize) });
});

// ---------------------------------------------------------------------------
// Jobs
// ---------------------------------------------------------------------------
router.get('/jobs', (req, res) => res.json(status()));
router.post('/jobs/:job', async (req, res) => {
  const job = req.params.job;
  if (!['predictions', 'review', 'reset'].includes(job)) throw new HttpError(404, 'Unknown job');
  if (job === 'reset' && req.body?.confirm !== 'RESET') throw new HttpError(400, 'Type RESET to confirm.');
  try {
    res.json(await runJob(job));
  } catch (e) {
    throw new HttpError(500, e.message);
  }
});

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------
// eslint-disable-next-line no-unused-vars
router.use((err, req, res, next) => {
  const status = err.status || 500;
  if (status >= 500) console.error(err);
  res.status(status).json({ error: err.message, errors: err.errors || [err.message] });
});
