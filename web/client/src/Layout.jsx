import { useQueryClient } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'framer-motion';
import { Activity, Building2, Columns3, Database, Handshake, LayoutDashboard, Plus, Search, Sparkles, Users } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';

import { useMeta } from './api.js';
import CommandPalette from './components/CommandPalette.jsx';
import { date } from './lib/format.js';

const NAV = [
  { group: 'CRM', items: [
    { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
    { to: '/pipeline', label: 'Pipeline board', icon: Columns3 },
    { to: '/opportunities', label: 'Opportunities', icon: Handshake },
    { to: '/accounts', label: 'Accounts', icon: Building2 },
    { to: '/team', label: 'Sales team', icon: Users },
  ] },
  { group: 'Manage', items: [{ to: '/new', label: 'Add / my entries', icon: Plus }] },
  { group: 'Analytics', items: [
    { to: '/insights', label: 'Win prediction', icon: Sparkles },
    { to: '/data', label: 'Data review', icon: Database },
  ] },
];

function JobChip() {
  const { data } = useMeta();
  const qc = useQueryClient();
  const wasRunning = useRef(false);
  const running = data?.jobs?.running;
  useEffect(() => { // when a re-score finishes, refresh everything so new probabilities show up
    if (wasRunning.current && !running) qc.invalidateQueries();
    wasRunning.current = !!running;
  }, [running, qc]);
  if (!data) return null;
  return (
    <span className="job-chip" title={data.jobs?.last ? `Last job: ${data.jobs.last.job} (${data.jobs.last.ok ? 'ok' : 'failed'})` : ''}>
      <span className={`dot ${running ? 'busy' : ''}`} />
      {running ? 'Re-scoring deals…' : `Data through ${date(data.snapshot)}`}
    </span>
  );
}

export default function Layout() {
  const [palette, setPalette] = useState(false);
  const loc = useLocation();
  const nav = useNavigate();
  const { data: meta } = useMeta();

  useEffect(() => {
    const h = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPalette((p) => !p); }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, []);

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-logo"><Activity size={19} /></div>
          <div><div className="brand-name">Pipeline CRM</div><div className="brand-sub">Sales intelligence</div></div>
        </div>
        {NAV.map((g) => (
          <div key={g.group}>
            <div className="nav-label">{g.group}</div>
            {g.items.map((it) => (
              <NavLink key={it.to} to={it.to} end={it.end} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                {({ isActive }) => (
                  <>
                    {isActive && <motion.span layoutId="nav-bg" className="nav-bg" transition={{ type: 'spring', stiffness: 420, damping: 34 }} />}
                    <it.icon size={18} /> {it.label}
                  </>
                )}
              </NavLink>
            ))}
          </div>
        ))}
        {meta && (
          <div className="sidebar-foot">
            <strong>{meta.opportunities?.toLocaleString()}</strong> opportunities<br />
            <strong>{meta.user_entries?.opps ?? 0}</strong> deals &amp; <strong>{meta.user_entries?.accounts ?? 0}</strong> accounts added or updated here
          </div>
        )}
      </aside>
      <div className="main">
        <header className="topbar">
          <button className="search-trigger" onClick={() => setPalette(true)}>
            <Search size={16} /> Search deals, accounts, reps…
            <span className="kbd">Ctrl K</span>
          </button>
          <div className="topbar-spacer" />
          <JobChip />
          <button className="btn primary" onClick={() => nav('/new')}><Plus size={16} /> New deal</button>
        </header>
        <AnimatePresence mode="wait">
          <motion.main key={loc.pathname} className="page" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                       exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.22 }}>
            <Outlet />
          </motion.main>
        </AnimatePresence>
      </div>
      <CommandPalette open={palette} onClose={() => setPalette(false)} />
    </div>
  );
}
