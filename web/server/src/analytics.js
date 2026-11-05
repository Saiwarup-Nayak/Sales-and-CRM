/**
 * Descriptive analytics over the master table (JS port of src/descriptive_analytics.py).
 * Revenue always means won revenue; open-deal value is an estimate from list price.
 */

export function wilson(k, n, z = 1.96) {
  if (!n) return [null, null];
  const p = k / n;
  const denom = 1 + (z * z) / n;
  const centre = (p + (z * z) / (2 * n)) / denom;
  const half = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / denom;
  return [Math.max(0, centre - half), Math.min(1, centre + half)];
}

const sum = (arr, f) => arr.reduce((s, r) => s + (f(r) ?? 0), 0);
const mean = (vals) => (vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null);

export function kpis(rows) {
  const won = rows.filter((r) => r.is_won);
  const lost = rows.filter((r) => r.is_lost);
  const open = rows.filter((r) => r.is_open);
  const closed = won.length + lost.length;
  const cycles = rows.filter((r) => r.is_closed && r.sales_cycle_days != null).map((r) => r.sales_cycle_days);
  return {
    total_opportunities: rows.length,
    closed_opportunities: closed,
    open_opportunities: open.length,
    won_deals: won.length,
    lost_deals: lost.length,
    win_rate: closed ? won.length / closed : null,
    won_revenue: sum(won, (r) => r.won_revenue),
    avg_won_deal: won.length ? sum(won, (r) => r.won_revenue) / won.length : null,
    open_pipeline_est_value: sum(open, (r) => r.est_open_value),
    active_reps: new Set(rows.map((r) => r.sales_agent)).size,
    avg_sales_cycle_days: mean(cycles),
  };
}

function summarise(key, group) {
  const won = group.filter((r) => r.is_won).length;
  const lost = group.filter((r) => r.is_lost).length;
  const open = group.filter((r) => r.is_open).length;
  const rev = sum(group, (r) => r.won_revenue);
  const [lo, hi] = wilson(won, won + lost);
  const cycles = group.filter((r) => r.sales_cycle_days != null).map((r) => r.sales_cycle_days);
  return {
    key, opportunities: group.length, open, won, lost,
    win_rate: won + lost ? won / (won + lost) : null, win_rate_lo: lo, win_rate_hi: hi,
    won_revenue: rev, avg_won_deal: won ? rev / won : null,
    revenue_per_closed_deal: won + lost ? rev / (won + lost) : null,
    open_pipeline_est_value: sum(group, (r) => r.est_open_value),
    avg_cycle_days: mean(cycles),
  };
}

/** Group rows by a key function and summarise each group, sorted by won revenue. */
export function summariseBy(rows, keyFn) {
  const groups = new Map();
  for (const r of rows) {
    const k = keyFn(r);
    if (k == null) continue;
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(r);
  }
  const total = sum(rows, (r) => r.won_revenue);
  return [...groups.entries()]
    .map(([k, g]) => ({ ...summarise(k, g), revenue_share: total ? sum(g, (r) => r.won_revenue) / total : null }))
    .sort((a, b) => b.won_revenue - a.won_revenue);
}

function monthRange(first, last) {
  const out = [];
  let [y, m] = first.split('-').map(Number);
  const [ly, lm] = last.split('-').map(Number);
  while (y < ly || (y === ly && m <= lm)) {
    out.push(`${y}-${String(m).padStart(2, '0')}`);
    m += 1;
    if (m > 12) { m = 1; y += 1; }
  }
  return out;
}

/** Won revenue / won / lost per close month, gap-filled. */
export function monthly(rows) {
  const closed = rows.filter((r) => r.is_closed && r.close_month);
  if (!closed.length) return [];
  const months = closed.map((r) => r.close_month).sort();
  const by = new Map(monthRange(months[0], months.at(-1)).map((m) => [m, { period: m, won_revenue: 0, won: 0, lost: 0 }]));
  for (const r of closed) {
    const b = by.get(r.close_month);
    b.won_revenue += r.won_revenue;
    if (r.is_won) b.won += 1; else b.lost += 1;
  }
  return [...by.values()].map((b) => ({ ...b, win_rate: b.won + b.lost ? b.won / (b.won + b.lost) : null }));
}

export function stages(rows) {
  const order = ['Prospecting', 'Engaging', 'Won', 'Lost'];
  return order.map((s) => {
    const g = rows.filter((r) => r.deal_stage === s);
    return {
      stage: s, count: g.length, share: rows.length ? g.length / rows.length : 0,
      value: s === 'Won' ? sum(g, (r) => r.won_revenue) : s === 'Lost' ? 0 : sum(g, (r) => r.est_open_value),
    };
  });
}

export function repPerformance(rows) {
  const reps = summariseBy(rows, (r) => r.sales_agent);
  const offices = Object.fromEntries(summariseBy(rows, (r) => r.regional_office).map((o) => [o.key, o.win_rate]));
  const info = new Map(rows.map((r) => [r.sales_agent, { manager: r.manager, regional_office: r.regional_office }]));
  return reps.map((r) => {
    const i = info.get(r.key);
    const ow = offices[i.regional_office];
    return { ...r, sales_agent: r.key, ...i, office_win_rate: ow,
             win_rate_vs_office_pp: r.win_rate != null && ow != null ? (r.win_rate - ow) * 100 : null };
  });
}
