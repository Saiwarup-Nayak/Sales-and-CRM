/**
 * SQLite access (node:sqlite) for the CRM store shared with the Python analytics jobs.
 * The joined, derived opportunity table ("master") is cached in memory and rebuilt
 * whenever the store's version counter changes.
 */
import { DatabaseSync } from 'node:sqlite';
import { DB_PATH, NOT_ASSIGNED } from './config.js';

let db = null;

export function open(dbPath = DB_PATH) {
  db = new DatabaseSync(dbPath);
  db.exec('PRAGMA busy_timeout = 8000; PRAGMA foreign_keys = ON;');
  db.exec(`CREATE TABLE IF NOT EXISTS predictions
           (opportunity_id TEXT PRIMARY KEY, win_probability REAL, scored_at TEXT)`);
  cache = { version: -1, master: null, snapshot: null };
  return db;
}

export const conn = () => {
  if (!db) throw new Error('Database not opened');
  return db;
};

export function version() {
  return Number(conn().prepare("SELECT value FROM meta WHERE key='version'").get().value);
}

export function meta() {
  return Object.fromEntries(conn().prepare('SELECT key, value FROM meta').all().map((r) => [r.key, r.value]));
}

export function bump() {
  conn().prepare("UPDATE meta SET value = CAST(value AS INTEGER) + 1 WHERE key='version'").run();
}

/** Run fn inside a transaction. */
export function tx(fn) {
  const d = conn();
  d.exec('BEGIN IMMEDIATE');
  try {
    const out = fn(d);
    d.exec('COMMIT');
    return out;
  } catch (e) {
    d.exec('ROLLBACK');
    throw e;
  }
}

// ---------------------------------------------------------------------------
// Master table (same derivations as src/preprocessing.add_derived_columns)
// ---------------------------------------------------------------------------
const DAY = 86400000;
const toMs = (d) => (d ? Date.parse(`${d}T00:00:00Z`) : null);
export const daysBetween = (a, b) => (a && b ? Math.round((toMs(b) - toMs(a)) / DAY) : null);

let cache = { version: -1, master: null, snapshot: null };

export function loadMaster() {
  // Writes bump the version; the Python scorer rewrites predictions, so its timestamp is part of the key.
  const scored = conn().prepare('SELECT MAX(scored_at) AS s FROM predictions').get().s ?? '';
  const v = `${version()}:${scored}`;
  if (cache.version === v && cache.master) return cache;
  const rows = conn().prepare(`
    SELECT o.opportunity_id, o.sales_agent, o.product, o.account, o.deal_stage, o.engage_date, o.close_date,
           o.close_value, o.source, o.created_at, o.updated_at,
           p.series, p.sales_price, t.manager, t.regional_office,
           a.sector, a.year_established, a.revenue, a.employees, a.office_location, a.subsidiary_of,
           pr.win_probability
    FROM opportunities o
    LEFT JOIN products p ON p.product = o.product
    LEFT JOIN sales_teams t ON t.sales_agent = o.sales_agent
    LEFT JOIN accounts a ON a.account = o.account
    LEFT JOIN predictions pr ON pr.opportunity_id = o.opportunity_id`).all();

  let snapshot = '';
  for (const r of rows) {
    if (r.close_date && r.close_date > snapshot) snapshot = r.close_date;
    if (r.engage_date && r.engage_date > snapshot) snapshot = r.engage_date;
  }
  const master = rows.map((r) => {
    const isWon = r.deal_stage === 'Won';
    const isLost = r.deal_stage === 'Lost';
    const isClosed = isWon || isLost;
    return {
      ...r,
      account_known: r.account != null,
      account: r.account ?? NOT_ASSIGNED,
      sector: r.sector ?? NOT_ASSIGNED,
      is_won: isWon, is_lost: isLost, is_closed: isClosed, is_open: !isClosed,
      outcome: isWon ? 'Won' : isLost ? 'Lost' : 'Open',
      won_revenue: isWon ? (r.close_value ?? 0) : 0,
      est_open_value: isClosed ? null : r.sales_price,
      sales_cycle_days: isClosed ? daysBetween(r.engage_date, r.close_date) : null,
      open_age_days: !isClosed && r.engage_date ? daysBetween(r.engage_date, snapshot) : null,
      close_month: r.close_date ? r.close_date.slice(0, 7) : null,
      win_probability: isClosed ? null : r.win_probability,
    };
  });
  cache = { version: v, master, snapshot };
  return cache;
}

export function lookups() {
  const d = conn();
  return {
    agents: d.prepare('SELECT * FROM sales_teams ORDER BY sales_agent').all(),
    products: d.prepare('SELECT * FROM products ORDER BY sales_price').all(),
    accounts: d.prepare('SELECT account FROM accounts ORDER BY account').all().map((r) => r.account),
    sectors: d.prepare('SELECT DISTINCT sector FROM accounts WHERE sector IS NOT NULL ORDER BY sector').all()
      .map((r) => r.sector),
    locations: d.prepare(`SELECT DISTINCT office_location FROM accounts WHERE office_location IS NOT NULL
                          ORDER BY office_location`).all().map((r) => r.office_location),
    offices: d.prepare('SELECT DISTINCT regional_office FROM sales_teams ORDER BY 1').all().map((r) => r.regional_office),
  };
}
