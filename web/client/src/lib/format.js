export const isNum = (v) => typeof v === 'number' && Number.isFinite(v);

export function money(v, { compact = true } = {}) {
  if (!isNum(v)) return '–';
  if (compact && Math.abs(v) >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  if (compact && Math.abs(v) >= 1e4) return `$${(v / 1e3).toFixed(1)}K`;
  return `$${Math.round(v).toLocaleString('en-US')}`;
}
export const moneyFull = (v) => (isNum(v) ? `$${Math.round(v).toLocaleString('en-US')}` : '–');
export const pct = (v, d = 1) => (isNum(v) ? `${(v * 100).toFixed(d)}%` : '–');
export const num = (v, d = 0) => (isNum(v) ? v.toLocaleString('en-US', { maximumFractionDigits: d }) : '–');

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export function date(iso) {
  if (!iso) return '–';
  const [y, m, d] = String(iso).slice(0, 10).split('-');
  return `${Number(d)} ${MONTHS[Number(m) - 1]} ${y}`;
}
export function monthLabel(period) {
  const [y, m] = period.split('-');
  return `${MONTHS[Number(m) - 1]} ${y.slice(2)}`;
}
export const axisMoney = (v) => (Math.abs(v) >= 1e6 ? `$${(v / 1e6).toFixed(1)}M` : Math.abs(v) >= 1e3 ? `$${Math.round(v / 1e3)}K` : `$${v}`);
export const initials = (name = '') => name.split(/\s+/).map((p) => p[0]).slice(0, 2).join('').toUpperCase();
export const title = (s = '') => String(s).replace(/\b\w/g, (c) => c.toUpperCase());
export const todayIso = () => new Date().toISOString().slice(0, 10);
/** New records default to the dataset's last date (so they line up with history), never after today. */
export const defaultDate = (snapshot) => (snapshot && snapshot < todayIso() ? snapshot : todayIso());
