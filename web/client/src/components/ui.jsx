import { animate, motion, useMotionValue, useTransform } from 'framer-motion';
import { AlertTriangle, Info, XCircle } from 'lucide-react';
import { useEffect, useId, useState } from 'react';

import { isNum } from '../lib/format.js';

const rise = { hidden: { opacity: 0, y: 14 }, show: (i = 0) => ({ opacity: 1, y: 0, transition: { delay: i * 0.05, duration: 0.45, ease: [0.22, 1, 0.36, 1] } }) };

/** Floating card: fades up on mount, lifts on hover. */
export function Card({ title, sub, actions, children, i = 0, float = true, className = '', style, ...rest }) {
  return (
    <motion.section
      className={`card ${float ? 'float' : ''} ${className}`}
      variants={rise} initial="hidden" animate="show" custom={i}
      whileHover={float ? { y: -4 } : undefined} transition={{ type: 'spring', stiffness: 300, damping: 24 }}
      style={style} {...rest}
    >
      {(title || actions) && (
        <div className="card-head">
          <div>
            {title && <div className="card-title">{title}</div>}
            {sub && <div className="card-sub">{sub}</div>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </motion.section>
  );
}

export function CountUp({ value, format = (v) => v, duration = 0.9 }) {
  const mv = useMotionValue(0);
  const text = useTransform(mv, (v) => (isNum(value) ? format(v) : '–'));
  useEffect(() => {
    if (!isNum(value)) return undefined;
    const ctl = animate(mv, value, { duration, ease: [0.22, 1, 0.36, 1] });
    return () => ctl.stop();
  }, [value, duration, mv]);
  return <motion.span>{text}</motion.span>;
}

export function KpiCard({ label, value, format, sub, icon: Icon, i = 0 }) {
  return (
    <Card className="kpi" i={i}>
      <div className="kpi-top">
        <span className="kpi-label">{label}</span>
        {Icon && <span className="kpi-icon"><Icon size={17} /></span>}
      </div>
      <div className="kpi-value" style={!format && typeof value === 'string' ? { fontSize: 19, marginTop: 12 } : undefined}>
        {format ? <CountUp value={value} format={format} /> : value}
      </div>
      {sub && <div className="kpi-sub">{sub}</div>}
      <div className="kpi-glow" />
    </Card>
  );
}

export const StagePill = ({ stage }) => <span className={`pill ${stage}`}>{stage}</span>;

export function Prob({ value }) {
  if (!isNum(value)) return <span className="muted">–</span>;
  return (
    <div className="prob" title="Model estimate. No better than chance on this dataset, so treat it as indicative only.">
      <div className="prob-track"><div className="prob-fill" style={{ width: `${value * 100}%` }} /></div>
      <span>{value.toFixed(2)}</span>
    </div>
  );
}

/** Segmented control with a sliding highlight. */
export function Seg({ options, value, onChange, getLabel = (o) => o }) {
  const id = useId();
  return (
    <div className="seg" role="radiogroup">
      {options.map((o) => (
        <button key={o} type="button" role="radio" aria-checked={value === o} className={value === o ? 'on' : ''}
                onClick={() => onChange(o)}>
          {value === o && <motion.span layoutId={`seg-${id}`} className="seg-bg" transition={{ type: 'spring', stiffness: 400, damping: 32 }} />}
          {getLabel(o)}
        </button>
      ))}
    </div>
  );
}

export function Chips({ options, value = [], onChange }) {
  const toggle = (o) => onChange(value.includes(o) ? value.filter((v) => v !== o) : [...value, o]);
  return (
    <div className="row" style={{ gap: 6 }}>
      {options.map((o) => (
        <button type="button" key={o} className={`chip ${value.includes(o) ? 'on' : ''}`} onClick={() => toggle(o)}>{o}</button>
      ))}
    </div>
  );
}

export function Field({ label, hint, children }) {
  return (
    <div className="field">
      {label && <label>{label}</label>}
      {children}
      {hint && <div className="hint">{hint}</div>}
    </div>
  );
}

export function Select({ value, onChange, options, placeholder, getLabel = (o) => o, getValue = (o) => o, ...rest }) {
  return (
    <select className="select" value={value ?? ''} onChange={(e) => onChange(e.target.value || null)} {...rest}>
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {options.map((o) => <option key={getValue(o)} value={getValue(o)}>{getLabel(o)}</option>)}
    </select>
  );
}

export const Input = (props) => <input className="input" {...props} />;

export function SearchInput({ value, onChange, placeholder, icon: Icon }) {
  return (
    <div className="input-icon" style={{ minWidth: 240, flex: 1 }}>
      {Icon && <Icon size={16} />}
      <input className="input" value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

export function Alert({ kind = 'info', title, children }) {
  const Icon = kind === 'warn' ? AlertTriangle : kind === 'error' ? XCircle : Info;
  return (
    <div className={`alert ${kind}`} role={kind === 'error' ? 'alert' : 'status'}>
      <Icon size={18} style={{ flex: 'none', marginTop: 1 }} />
      <div>{title && <div className="strong">{title}</div>}{children}</div>
    </div>
  );
}

export const Skeleton = ({ h = 16, w = '100%', style }) => <div className="skeleton" style={{ height: h, width: w, ...style }} />;

export function Loading({ rows = 3, h = 220 }) {
  return (
    <div className="stack">
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} h={h / rows} />)}
    </div>
  );
}

export const Empty = ({ children = 'Nothing to show.' }) => <div className="empty">{children}</div>;

export function PageHead({ title, sub, children }) {
  return (
    <motion.div className="page-head" initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
      <div><h1>{title}</h1>{sub && <p>{sub}</p>}</div>
      {children && <div className="row">{children}</div>}
    </motion.div>
  );
}

export function ChartTip({ active, payload, label, rows, head }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="chart-tip">
      <div className="h">{head ? head(d, label) : label}</div>
      {rows(d, payload).map(([k, v]) => <div className="r" key={k}><span>{k}</span><b>{v}</b></div>)}
    </div>
  );
}

export function DetailGrid({ items }) {
  return (
    <div className="detail-grid">
      {items.map(([k, v]) => <div key={k}><div className="k">{k}</div><div className="v">{v ?? '–'}</div></div>)}
    </div>
  );
}

export function useDebounced(value, ms = 250) {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t); }, [value, ms]);
  return v;
}
