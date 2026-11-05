/**
 * Business-rule validation for new/updated records.
 * Mirrors src/crm_store.py (validate_opportunity / validate_account) so both apps enforce the same rules.
 */
import { CLOSED_STAGES, NOT_ASSIGNED, OPEN_STAGES, STAGES } from './config.js';

const ISO = /^\d{4}-\d{2}-\d{2}$/;
const blank = (v) => v === undefined || v === null || v === '';
const todayIso = () => new Date().toISOString().slice(0, 10);

export function normaliseDate(v) {
  if (blank(v)) return null;
  const s = String(v).slice(0, 10);
  return ISO.test(s) && !Number.isNaN(Date.parse(`${s}T00:00:00Z`)) ? s : 'invalid';
}

/**
 * @param rec  {sales_agent, product, account, deal_stage, engage_date, close_date, close_value}
 * @param ctx  {agents:Set, products:Set, accounts:Set}
 * @returns string[] problems (empty = valid)
 */
export function validateOpportunity(rec, ctx, today = todayIso()) {
  const errors = [];
  const stage = rec.deal_stage;
  const engage = normaliseDate(rec.engage_date);
  const close = normaliseDate(rec.close_date);
  const value = blank(rec.close_value) ? null : Number(rec.close_value);
  const acc = blank(rec.account) || rec.account === NOT_ASSIGNED ? null : rec.account;

  if (!ctx.agents.has(rec.sales_agent)) errors.push('Choose a sales agent from the sales team.');
  if (!ctx.products.has(rec.product)) errors.push('Choose a product from the product catalogue.');
  if (acc && !ctx.accounts.has(acc)) errors.push(`Account '${acc}' does not exist. Add it first under New account.`);
  if (!STAGES.includes(stage)) errors.push(`Stage must be one of ${STAGES.join(', ')}.`);
  if (engage === 'invalid' || close === 'invalid') errors.push('Dates must be valid (YYYY-MM-DD).');
  if (['Engaging', 'Won', 'Lost'].includes(stage) && !engage) {
    errors.push('An engage date is required once a deal has reached Engaging.');
  }
  if (stage === 'Prospecting' && engage) {
    errors.push('Prospecting deals have not been engaged yet, so leave the engage date empty.');
  }
  if (CLOSED_STAGES.includes(stage)) {
    if (!close) errors.push('Closed deals (Won/Lost) need a close date.');
    if (!acc) errors.push('Closed deals must be linked to an account.');
  }
  if (OPEN_STAGES.includes(stage) && (close || value !== null)) {
    errors.push('Open deals cannot have a close date or close value.');
  }
  if (value !== null && Number.isNaN(value)) errors.push('Close value must be a number.');
  if (stage === 'Won' && !(value > 0)) errors.push('Won deals need a close value greater than 0.');
  if (stage === 'Lost' && value !== null && value !== 0) errors.push('Lost deals have a close value of 0.');
  if (engage && close && engage !== 'invalid' && close !== 'invalid' && engage > close) {
    errors.push('The engage date cannot be after the close date.');
  }
  for (const [name, d] of [['Engage date', engage], ['Close date', close]]) {
    if (d && d !== 'invalid' && d > today) errors.push(`${name} cannot be in the future.`);
  }
  return errors;
}

/** Cleaned row ready for storage (Lost -> value 0, open -> no close fields). */
export function cleanOpportunity(rec) {
  const stage = rec.deal_stage;
  const closed = CLOSED_STAGES.includes(stage);
  const acc = blank(rec.account) || rec.account === NOT_ASSIGNED ? null : rec.account;
  let value = blank(rec.close_value) ? null : Number(rec.close_value);
  if (stage === 'Lost') value = 0;
  return {
    sales_agent: rec.sales_agent, product: rec.product, account: acc, deal_stage: stage,
    engage_date: normaliseDate(rec.engage_date), close_date: closed ? normaliseDate(rec.close_date) : null,
    close_value: closed ? value : null,
  };
}

export function validateAccount(rec, existingAccounts, currentYear = new Date().getFullYear()) {
  const errors = [];
  const name = String(rec.account ?? '').trim();
  const lower = new Set([...existingAccounts].map((a) => a.toLowerCase()));
  if (!name) errors.push('Account name is required.');
  else if (lower.has(name.toLowerCase()) || name === NOT_ASSIGNED) errors.push(`An account named '${name}' already exists.`);
  if (!String(rec.sector ?? '').trim()) errors.push('Sector is required.');
  if (!blank(rec.year_established)) {
    const y = Number(rec.year_established);
    if (!(y >= 1800 && y <= currentYear)) errors.push('Year established looks implausible.');
  }
  for (const f of ['revenue', 'employees']) {
    if (!blank(rec[f]) && !(Number(rec[f]) >= 0)) errors.push(`${f[0].toUpperCase()}${f.slice(1)} cannot be negative.`);
  }
  if (!blank(rec.subsidiary_of) && !existingAccounts.has(rec.subsidiary_of)) {
    errors.push('Parent company must be an existing account.');
  }
  return errors;
}
