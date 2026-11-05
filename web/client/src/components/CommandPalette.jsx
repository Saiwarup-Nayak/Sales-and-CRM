import { AnimatePresence, motion } from 'framer-motion';
import { Building2, CornerDownLeft, Handshake, LayoutDashboard, Plus, Search, User } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useApi, qs } from '../api.js';
import { useDrawers } from './Drawers.jsx';
import { StagePill, useDebounced } from './ui.jsx';

const PAGES = [
  { label: 'Dashboard', to: '/', icon: LayoutDashboard },
  { label: 'Pipeline board', to: '/pipeline', icon: Handshake },
  { label: 'Opportunities', to: '/opportunities', icon: Handshake },
  { label: 'Accounts', to: '/accounts', icon: Building2 },
  { label: 'Sales team', to: '/team', icon: User },
  { label: 'Add new entry', to: '/new', icon: Plus },
];

export default function CommandPalette({ open, onClose }) {
  const [q, setQ] = useState('');
  const [sel, setSel] = useState(0);
  const dq = useDebounced(q, 180);
  const inputRef = useRef(null);
  const nav = useNavigate();
  const drawers = useDrawers();
  const { data } = useApi(['search', dq], `/search${qs({ q: dq })}`, { enabled: open && dq.length >= 2 });

  useEffect(() => { if (open) { setQ(''); setSel(0); } }, [open]);

  const items = useMemo(() => {
    const ql = q.toLowerCase();
    const out = PAGES.filter((p) => !ql || p.label.toLowerCase().includes(ql))
      .map((p) => ({ group: 'Go to', key: p.to, label: p.label, icon: p.icon, run: () => nav(p.to) }));
    if (dq.length >= 2 && data) {
      data.opportunities.forEach((o) => out.push({ group: 'Opportunities', key: o.opportunity_id, label: `${o.opportunity_id} · ${o.product}`,
        sub: `${o.account} · ${o.sales_agent}`, stage: o.deal_stage, icon: Handshake, run: () => drawers.openDeal(o.opportunity_id) }));
      data.accounts.forEach((a) => out.push({ group: 'Accounts', key: `a-${a}`, label: a, icon: Building2, run: () => drawers.openAccount(a) }));
      data.reps.forEach((r) => out.push({ group: 'Sales reps', key: `r-${r.sales_agent}`, label: r.sales_agent,
        sub: `${r.regional_office} · ${r.manager}`, icon: User, run: () => drawers.openRep(r.sales_agent) }));
    }
    return out;
  }, [q, dq, data, nav, drawers]);

  useEffect(() => setSel(0), [q]);
  const go = (it) => { onClose(); it.run(); };
  const onKey = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSel((s) => Math.min(s + 1, items.length - 1)); }
    if (e.key === 'ArrowUp') { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
    if (e.key === 'Enter' && items[sel]) go(items[sel]);
    if (e.key === 'Escape') onClose();
  };
  let lastGroup = null;
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div className="overlay" style={{ zIndex: 60 }} onClick={onClose} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
          <motion.div className="palette" role="dialog" aria-label="Search" style={{ x: '-50%' }}
                      initial={{ opacity: 0, y: -10, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -8, scale: 0.98 }}
                      transition={{ type: 'spring', stiffness: 420, damping: 32 }}>
            <div className="palette-search">
              <Search size={18} />
              <input ref={inputRef} autoFocus value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onKey}
                     placeholder="Search deals, accounts, reps or jump to a page..." />
            </div>
            <div className="palette-list">
              {items.length === 0 && <div className="empty">No matches for “{q}”.</div>}
              {items.map((it, i) => {
                const header = it.group !== lastGroup ? <div className="palette-group" key={`g-${it.group}`}>{it.group}</div> : null;
                lastGroup = it.group;
                const Icon = it.icon;
                return [header, (
                  <div key={it.key} className={`palette-item ${i === sel ? 'on' : ''}`} onMouseEnter={() => setSel(i)} onClick={() => go(it)}>
                    <Icon size={17} color="#52514e" />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div>{it.label}</div>
                      {it.sub && <div className="sub">{it.sub}</div>}
                    </div>
                    {it.stage && <StagePill stage={it.stage} />}
                    {i === sel && <CornerDownLeft size={15} color="#898781" />}
                  </div>
                )];
              })}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
