import { Target, Trophy, Users } from 'lucide-react';
import { useState } from 'react';
import { CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from 'recharts';

import { qs, useApi, useLookups } from '../api.js';
import { useDrawers } from '../components/Drawers.jsx';
import DataTable from '../components/DataTable.jsx';
import { Card, ChartTip, KpiCard, Loading, PageHead, Seg } from '../components/ui.jsx';
import { initials, money, moneyFull, num, pct } from '../lib/format.js';
import { C } from '../lib/palette.js';

export default function Team() {
  const { data: lk } = useLookups();
  const [office, setOffice] = useState('All');
  const { data } = useApi(['team', office], `/team${qs({ office: office === 'All' ? null : office })}`);
  const { openRep } = useDrawers();
  const [sort, setSort] = useState({ key: 'won_revenue', dir: 'desc' });

  if (!data) return <><PageHead title="Sales team" /><Loading rows={3} h={360} /></>;
  const reps = [...data.reps].sort((a, b) => ((a[sort.key] ?? -1) > (b[sort.key] ?? -1) ? 1 : -1) * (sort.dir === 'asc' ? 1 : -1));
  const best = [...data.reps].sort((a, b) => b.won_revenue - a.won_revenue)[0];
  const eff = data.reps.filter((r) => r.won + r.lost >= 30).sort((a, b) => b.win_rate - a.win_rate)[0];
  const maxRev = Math.max(...data.reps.map((r) => r.won_revenue), 1);
  const scatter = data.reps.map((r) => ({ ...r, closed: r.won + r.lost }));

  const columns = [
    { key: 'sales_agent', label: 'Rep', sortable: true, render: (r) => (
      <div className="row" style={{ flexWrap: 'nowrap' }}><div className="avatar">{initials(r.sales_agent)}</div><span className="strong">{r.sales_agent}</span></div>) },
    { key: 'regional_office', label: 'Office', sortable: true },
    { key: 'manager', label: 'Manager', sortable: true },
    { key: 'opportunities', label: 'Deals', num: true, sortable: true },
    { key: 'open', label: 'Open', num: true, sortable: true },
    { key: 'won', label: 'Won', num: true, sortable: true },
    { key: 'win_rate', label: 'Win rate', num: true, sortable: true, render: (r) => pct(r.win_rate) },
    { key: 'win_rate_vs_office_pp', label: 'vs office', num: true, sortable: true, render: (r) => (
      <span style={{ color: r.win_rate_vs_office_pp >= 0 ? 'var(--good-ink)' : 'var(--critical)' }}>
        {r.win_rate_vs_office_pp >= 0 ? '+' : ''}{r.win_rate_vs_office_pp?.toFixed(1)} pp</span>) },
    { key: 'won_revenue', label: 'Won revenue', sortable: true, render: (r) => (
      <div className="row" style={{ flexWrap: 'nowrap', gap: 8 }}>
        <div className="bar-inline" style={{ width: 90 }}><div style={{ width: `${(r.won_revenue / maxRev) * 100}%` }} /></div>
        <span style={{ fontVariantNumeric: 'tabular-nums' }}>{money(r.won_revenue)}</span></div>) },
    { key: 'revenue_per_closed_deal', label: 'Revenue / closed deal', num: true, sortable: true, render: (r) => moneyFull(r.revenue_per_closed_deal) },
  ];

  return (
    <>
      <PageHead title="Sales team" sub="Compare win rate and revenue per closed deal, not just total revenue, because reps handle different volumes.">
        <Seg options={['All', ...(lk?.offices ?? [])]} value={office} onChange={setOffice} />
      </PageHead>
      <div className="grid grid-kpi">
        <KpiCard i={0} label="Active reps" value={data.reps.length} format={(v) => Math.round(v)} icon={Users} sub={`${new Set(data.reps.map((r) => r.manager)).size} managers`} />
        <KpiCard i={1} label="Top by revenue" value={best?.sales_agent ?? '–'} icon={Trophy} sub={best ? money(best.won_revenue) : ''} />
        <KpiCard i={2} label="Top by win rate" value={eff?.sales_agent ?? '–'} icon={Target} sub={eff ? `${pct(eff.win_rate)} (≥30 closed)` : ''} />
        <KpiCard i={3} label="Team win rate" value={data.kpis.win_rate} format={(v) => pct(v)} sub={`${num(data.kpis.closed_opportunities)} closed deals`} />
      </div>

      <Card i={2} title="Volume vs win rate" sub="Each dot is a rep (size = won revenue). Click a dot to open the scorecard." style={{ marginBottom: 16 }}>
        <ResponsiveContainer width="100%" height={320}>
          <ScatterChart margin={{ left: 0, right: 16, top: 10, bottom: 10 }}>
            <CartesianGrid />
            <XAxis type="number" dataKey="closed" name="Closed deals" tickLine={false} axisLine={false}
                   label={{ value: 'Closed deals (volume)', position: 'insideBottom', offset: -6, fill: C.muted, fontSize: 12 }} />
            <YAxis type="number" dataKey="win_rate" domain={['auto', 'auto']} tickFormatter={(v) => `${Math.round(v * 100)}%`} width={46} tickLine={false} axisLine={false} />
            <ZAxis type="number" dataKey="won_revenue" range={[60, 420]} />
            <ReferenceLine y={data.kpis.win_rate} stroke={C.orange} strokeWidth={1.5}
                           label={{ value: `team avg ${pct(data.kpis.win_rate)}`, position: 'insideTopLeft', fill: C.ink2, fontSize: 12 }} />
            <Tooltip content={<ChartTip head={(d) => d.sales_agent} rows={(d) => [['Closed deals', num(d.closed)], ['Win rate', pct(d.win_rate)], ['Won revenue', money(d.won_revenue)], ['Office', d.regional_office]]} />} />
            <Scatter data={scatter} fill={C.blue} fillOpacity={0.85} stroke="#fff" strokeWidth={2} cursor="pointer" onClick={(d) => openRep(d.sales_agent)} />
          </ScatterChart>
        </ResponsiveContainer>
      </Card>

      <Card float={false} title="Scorecard" sub="Click a rep for monthly revenue and product mix">
        <DataTable columns={columns} rows={reps} onRowClick={(r) => openRep(r.sales_agent)} rowKey={(r) => r.sales_agent}
                   sort={sort} onSort={setSort} maxHeight={640} />
      </Card>
    </>
  );
}
