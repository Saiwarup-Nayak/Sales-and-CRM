/**
 * API integration test against a temporary COPY of data/crm_app.db (the real database is never touched).
 */
import assert from 'node:assert/strict';
import { copyFileSync, existsSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { after, before, test } from 'node:test';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const realDb = path.resolve(here, '..', '..', '..', 'data', 'crm_app.db');
const dir = mkdtempSync(path.join(tmpdir(), 'crm-test-'));
const testDb = path.join(dir, 'crm_app.db');
process.env.CRM_DB_PATH = testDb;
process.env.CRM_DISABLE_RESCORE = '1';

let server;
let base;

before(async () => {
  if (!existsSync(realDb)) throw new Error('Run the app once (or `python -m src.web_export all`) to create the database.');
  copyFileSync(realDb, testDb);
  const express = (await import('express')).default;
  const db = await import('../src/db.js');
  const { router } = await import('../src/routes.js');
  db.open(testDb);
  const app = express();
  app.use(express.json());
  app.use('/api', router);
  await new Promise((resolve) => { server = app.listen(0, resolve); });
  base = `http://127.0.0.1:${server.address().port}/api`;
});

after(() => {
  server?.close();
  try { rmSync(dir, { recursive: true, force: true }); } catch { /* Windows may hold the file briefly */ }
});

const json = async (url, opts = {}) => {
  const res = await fetch(base + url, { headers: { 'content-type': 'application/json' }, ...opts });
  return { status: res.status, body: res.status === 204 ? null : await res.json() };
};

test('dashboard KPIs match the known dataset totals', async () => {
  const { body } = await json('/dashboard');
  assert.equal(body.total, 8800);
  assert.equal(body.kpis.won_deals, 4238);
  assert.equal(body.kpis.lost_deals, 2473);
  assert.ok(Math.abs(body.kpis.win_rate - 4238 / 6711) < 1e-9);
  assert.equal(Math.round(body.kpis.won_revenue), 10005534);
  assert.equal(body.monthly.length, 10);
});

test('dashboard filters by office', async () => {
  const all = (await json('/dashboard')).body;
  const east = (await json('/dashboard?offices=East')).body;
  assert.ok(east.filtered < all.filtered && east.filtered > 0);
});

test('create, update, list and delete an opportunity', async () => {
  const bad = await json('/opportunities', { method: 'POST', body: JSON.stringify({ deal_stage: 'Won' }) });
  assert.equal(bad.status, 422);
  assert.ok(bad.body.errors.length >= 3);

  const created = await json('/opportunities', { method: 'POST', body: JSON.stringify({
    sales_agent: 'Darcel Schlecht', product: 'GTX Pro', account: 'Acme Corporation', deal_stage: 'Engaging',
    engage_date: '2017-12-01' }) });
  assert.equal(created.status, 201);
  const id = created.body.opportunity_id;

  const won = await json(`/opportunities/${id}`, { method: 'PATCH', body: JSON.stringify({
    deal_stage: 'Won', close_date: '2017-12-20', close_value: 5000 }) });
  assert.equal(won.status, 200);
  const again = await json(`/opportunities/${id}`, { method: 'PATCH', body: JSON.stringify({ deal_stage: 'Lost' }) });
  assert.equal(again.status, 409);

  const k = (await json('/dashboard')).body.kpis;
  assert.equal(k.won_deals, 4239);

  const entries = (await json('/entries')).body;
  assert.ok(entries.opportunities.some((o) => o.opportunity_id === id));
  assert.equal((await json(`/opportunities/${id}`, { method: 'DELETE' })).status, 204);
  const github = (await json('/opportunities?pageSize=1')).body.rows[0].opportunity_id;
  assert.equal((await json(`/opportunities/${github}`, { method: 'DELETE' })).status, 403);
});

test('accounts: create, reject duplicate, delete', async () => {
  const rec = { account: 'Zeta Test Co', sector: 'Retail', year_established: 2001, revenue: 10, employees: 50 };
  assert.equal((await json('/accounts', { method: 'POST', body: JSON.stringify(rec) })).status, 201);
  assert.equal((await json('/accounts', { method: 'POST', body: JSON.stringify(rec) })).status, 422);
  const detail = (await json(`/accounts/${encodeURIComponent('Zeta Test Co')}`)).body;
  assert.equal(detail.account.sector, 'retail');
  assert.equal((await json(`/accounts/${encodeURIComponent('Zeta Test Co')}`, { method: 'DELETE' })).status, 204);
});

test('opportunity list paginates, filters and searches', async () => {
  const { body } = await json('/opportunities?stages=Won&pageSize=10&page=2&sort=close_value&dir=desc');
  assert.equal(body.rows.length, 10);
  assert.ok(body.rows.every((r) => r.deal_stage === 'Won'));
  assert.equal(body.total, 4238);
  const s = (await json('/search?q=acme')).body;
  assert.ok(s.accounts.includes('Acme Corporation'));
});
