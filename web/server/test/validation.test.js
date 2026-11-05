import assert from 'node:assert/strict';
import { test } from 'node:test';

import { kpis, monthly, summariseBy, wilson } from '../src/analytics.js';
import { cleanOpportunity, validateAccount, validateOpportunity } from '../src/validation.js';

const ctx = { agents: new Set(['Ann']), products: new Set(['GTX Basic']), accounts: new Set(['Acme']) };
const base = (o = {}) => ({ sales_agent: 'Ann', product: 'GTX Basic', account: 'Acme', deal_stage: 'Engaging',
  engage_date: '2017-03-01', close_date: null, close_value: null, ...o });
const TODAY = '2020-01-01';

test('valid open deal passes', () => {
  assert.deepEqual(validateOpportunity(base(), ctx, TODAY), []);
});

const cases = [
  [{ sales_agent: 'Nobody' }, 'sales agent'],
  [{ product: 'X' }, 'product'],
  [{ account: 'Ghost' }, 'does not exist'],
  [{ engage_date: null }, 'engage date is required'],
  [{ deal_stage: 'Prospecting' }, 'leave the engage date empty'],
  [{ deal_stage: 'Won', close_date: '2017-03-05', close_value: 0 }, 'greater than 0'],
  [{ deal_stage: 'Won', close_value: 10 }, 'need a close date'],
  [{ deal_stage: 'Won', close_date: '2017-02-01', close_value: 10 }, 'after the close date'],
  [{ deal_stage: 'Lost', close_date: '2017-03-05', account: null }, 'linked to an account'],
  [{ close_date: '2017-03-05' }, 'Open deals cannot'],
  [{ engage_date: '2999-01-01' }, 'future'],
  [{ engage_date: '2017-13-45' }, 'valid'],
  [{ deal_stage: 'Maybe' }, 'Stage must be'],
];
for (const [change, msg] of cases) {
  test(`rejects: ${msg}`, () => {
    const errs = validateOpportunity(base(change), ctx, TODAY);
    assert.ok(errs.some((e) => e.toLowerCase().includes(msg.toLowerCase())), JSON.stringify(errs));
  });
}

test('lost deals are stored with value 0 and open deals without close fields', () => {
  assert.equal(cleanOpportunity(base({ deal_stage: 'Lost', close_date: '2017-03-05' })).close_value, 0);
  const open = cleanOpportunity(base({ close_value: 99 }));
  assert.equal(open.close_value, null);
  assert.equal(open.close_date, null);
});

test('account validation', () => {
  const existing = new Set(['Acme']);
  assert.ok(validateAccount({ account: 'acme', sector: 'retail' }, existing).length);
  assert.ok(validateAccount({ account: 'New', sector: '' }, existing).length);
  assert.ok(validateAccount({ account: 'New', sector: 'x', employees: -1 }, existing).length);
  assert.ok(validateAccount({ account: 'New', sector: 'x', subsidiary_of: 'Ghost' }, existing).length);
  assert.deepEqual(validateAccount({ account: 'New', sector: 'x', year_established: 2001 }, existing, 2026), []);
});

const rows = [
  { sales_agent: 'A', product: 'P', is_won: true, is_lost: false, is_open: false, is_closed: true, won_revenue: 100,
    est_open_value: null, sales_cycle_days: 10, close_month: '2017-01' },
  { sales_agent: 'A', product: 'P', is_won: false, is_lost: true, is_open: false, is_closed: true, won_revenue: 0,
    est_open_value: null, sales_cycle_days: 20, close_month: '2017-03' },
  { sales_agent: 'B', product: 'Q', is_won: false, is_lost: false, is_open: true, is_closed: false, won_revenue: 0,
    est_open_value: 50, sales_cycle_days: null, close_month: null },
];

test('kpis separate won revenue from open pipeline estimate', () => {
  const k = kpis(rows);
  assert.equal(k.won_revenue, 100);
  assert.equal(k.open_pipeline_est_value, 50);
  assert.equal(k.win_rate, 0.5);
  assert.equal(k.avg_sales_cycle_days, 15);
  assert.equal(k.active_reps, 2);
});

test('monthly series is gap-filled', () => {
  const m = monthly(rows);
  assert.deepEqual(m.map((x) => x.period), ['2017-01', '2017-02', '2017-03']);
  assert.equal(m[1].won_revenue, 0);
});

test('summariseBy and wilson interval', () => {
  const s = summariseBy(rows, (r) => r.sales_agent);
  assert.equal(s[0].key, 'A');
  assert.equal(s[0].win_rate, 0.5);
  const [lo, hi] = wilson(50, 100);
  assert.ok(lo > 0.40 && lo < 0.41 && hi > 0.59 && hi < 0.60);
});
