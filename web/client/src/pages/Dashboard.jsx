import { motion } from 'framer-motion';
import { CalendarClock, CircleDollarSign, Gauge, Layers, Target, Trophy, Users } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ErrorBar, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import { qs, useApi, useLookups } from '../api.js';
import { useDrawers } from '../components/Drawers.jsx';
import { Card, ChartTip, Chips, Field, Input, KpiCard, Loading, PageHead, Prob, StagePill } from '../components/ui.jsx';
import { axisMoney, date, money, moneyFull, monthLabel, num, pct, title } from '../lib/format.js';
import { C, STAGE_COLORS } from '../lib/palette.js';

const tickProps = { tickLine: false, axisLine: false };

export default function Dashboard() {
  const { data: lk } = useLookups();
  const [offices, setOffices] = useState([]);
  const [products, setProducts] = useState([]);
  const [range, setRange] = useState({ from: '', to: '' });
  const { data, isLoading, isFetching } = useApi(['dashboard', offices, products, range],
    `/dashboard${qs({ offices, products, from: range.from, to: range.to })}`);
  const nav = useNavigate();
  const { openRep, openDeal } = useDrawers();

  const officeData = useMemo(() => (data?.by_office ?? []).map((o) => ({
    ...o, err: [o.win_rate - o.win_rate_lo, o.win_rate_hi - o.win_rate] })), [data]);

  if (isLoading || !data) return <><PageHead title="Dashboard" sub="Loading sales performance…" /><Loading rows={4} h={400} /></>;
  const k = data.kpis;
  const sortedProducts = [...data.by_product].sort((a, b) => b.won_revenue - a.won_revenue);
  const maxStage = Math.max(...data.stages.map((s) => s.count), 1);

  return (
    <>
      <PageHead title="Dashboard"
                sub={`Sales performance across ${data.filtered.toLocaleString()} of ${data.total.toLocaleString()} opportunities · data through ${date(data.snapshot)}`} />

      <Card float={false} className="mt" style={{ marginTop: 0, marginBottom: 16, padding: '14px 16px', opacity: isFetching ? 0.85 : 1 }}>
        <div className="row" style={{ alignItems: 'flex-end', gap: 18 }}>
          <Field label="Closed from">
            <Input type="date" min={data.date_bounds.min} max={data.date_bounds.max} value={range.from}
                   onChange={(e) => setRange((r) => ({ ...r, from: e.target.value }))} />
          </Field>
          <Field label="Closed to">
            <Input type="date" min={data.date_bounds.min} max={data.date_bounds.max} value={range.to}
                   onChange={(e) => setRange((r) => ({ ...r, to: e.target.value }))} />
          </Field>
          <Field label="Regional office"><Chips options={lk?.offices ?? []} value={offices} onChange={setOffices} /></Field>
          <Field label="Product"><Chips options={(lk?.products ?? []).map((p) => p.product)} value={products} onChange={setProducts} /></Field>
          {(offices.length || products.length || range.from || range.to) ? (
            <button className="btn ghost sm" onClick={() => { setOffices([]); setProducts([]); setRange({ from: '', to: '' }); }}>Clear filters</button>
          ) : null}
        </div>
        <div className="muted small" style={{ marginTop: 8 }}>The date range applies to closed deals. Open deals have no close date, so they always count toward the pipeline.</div>
      </Card>

      <div className="grid grid-kpi">
        <KpiCard i={0} label="Won revenue" value={k.won_revenue} format={money} icon={CircleDollarSign} sub={`${num(k.won_deals)} won deals`} />
        <KpiCard i={1} label="Win rate" value={k.win_rate} format={(v) => pct(v)} icon={Target} sub={`of ${num(k.closed_opportunities)} closed deals`} />
        <KpiCard i={2} label="Avg won deal" value={k.avg_won_deal} format={money} icon={Trophy} sub="realised value" />
        <KpiCard i={3} label="Open pipeline (est.)" value={k.open_pipeline_est_value} format={money} icon={Layers} sub={`${num(k.open_opportunities)} open deals at list price`} />
        <KpiCard i={4} label="Avg sales cycle" value={k.avg_sales_cycle_days} format={(v) => `${Math.round(v)} days`} icon={CalendarClock} sub="engage → close" />
        <KpiCard i={5} label="Active reps" value={k.active_reps} format={(v) => Math.round(v)} icon={Users} sub="with at least one deal" />
      </div>

      <div className="grid grid-3-2">
        <Card i={1} title="Monthly won revenue" sub="Realised revenue by close month">
          <ResponsiveContainer width="100%" height={290}>
            <AreaChart data={data.monthly} margin={{ left: 0, right: 8, top: 8 }}>
              <defs>
                <linearGradient id="revFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={C.blue} stopOpacity={0.28} />
                  <stop offset="100%" stopColor={C.blue} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="period" tickFormatter={monthLabel} {...tickProps} />
              <YAxis tickFormatter={axisMoney} width={56} {...tickProps} />
              <Tooltip content={<ChartTip head={(d) => monthLabel(d.period)} rows={(d) => [['Won revenue', moneyFull(d.won_revenue)], ['Won deals', num(d.won)], ['Win rate', pct(d.win_rate)]]} />} />
              <Area type="linear" dataKey="won_revenue" stroke={C.blue} strokeWidth={2.5} fill="url(#revFill)"
                    dot={{ r: 4, fill: C.blue, stroke: '#fff', strokeWidth: 2 }} activeDot={{ r: 7, stroke: '#fff', strokeWidth: 3 }}
                    animationDuration={900} />
            </AreaChart>
          </ResponsiveContainer>
        </Card>

        <Card i={2} title="Deals by stage" sub="Current snapshot. Click a stage to see its deals.">
          <div className="stack" style={{ gap: 14, paddingTop: 6 }}>
            {data.stages.map((s, idx) => (
              <div key={s.stage} style={{ cursor: 'pointer' }} onClick={() => nav(`/opportunities?stages=${s.stage}`)}>
                <div className="row" style={{ justifyContent: 'space-between', marginBottom: 6 }}>
                  <StagePill stage={s.stage} />
                  <span className="small ink2"><b className="strong" style={{ color: '#0b0b0b' }}>{num(s.count)}</b> · {pct(s.share)} · {money(s.value)}{s.stage === 'Won' ? '' : s.stage === 'Lost' ? '' : ' est.'}</span>
                </div>
                <div className="bar-inline" style={{ height: 12 }}>
                  <motion.div initial={{ width: 0 }} animate={{ width: `${(s.count / maxStage) * 100}%` }}
                              transition={{ delay: 0.15 + idx * 0.08, duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
                              style={{ background: STAGE_COLORS[s.stage] }} />
                </div>
              </div>
            ))}
            <div className="muted small">Snapshot of each deal’s current stage, not stage-to-stage conversion. The data has no stage history.</div>
          </div>
        </Card>
      </div>

      <div className="grid grid-2 mt">
        <Card i={3} title="Won revenue by product">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={sortedProducts} layout="vertical" margin={{ left: 8, right: 30 }} barCategoryGap={7}>
              <CartesianGrid horizontal={false} />
              <XAxis type="number" tickFormatter={axisMoney} {...tickProps} />
              <YAxis type="category" dataKey="key" width={104} {...tickProps} />
              <Tooltip content={<ChartTip rows={(d) => [['Won revenue', moneyFull(d.won_revenue)], ['Won deals', num(d.won)], ['Win rate', pct(d.win_rate)], ['Avg deal', moneyFull(d.avg_won_deal)]]} />} />
              <Bar dataKey="won_revenue" fill={C.blue} radius={[0, 6, 6, 0]} animationDuration={800} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
        <Card i={4} title="Win rate by regional office" sub="Whiskers show the 95% confidence interval">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={officeData} margin={{ left: 0, right: 8, top: 10 }} barCategoryGap="30%">
              <CartesianGrid vertical={false} />
              <XAxis dataKey="key" {...tickProps} />
              <YAxis domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} width={44} {...tickProps} />
              <Tooltip content={<ChartTip rows={(d) => [['Win rate', pct(d.win_rate)], ['95% CI', `${pct(d.win_rate_lo)} – ${pct(d.win_rate_hi)}`], ['Won / lost', `${num(d.won)} / ${num(d.lost)}`], ['Won revenue', money(d.won_revenue)]]} />} />
              <Bar dataKey="win_rate" fill={C.blue} radius={[6, 6, 0, 0]} animationDuration={800}>
                <ErrorBar dataKey="err" width={10} strokeWidth={1.5} stroke={C.ink2} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <div className="grid grid-2 mt">
        <Card i={5} title="Top 10 sales reps" sub="By won revenue. Click a bar for the rep’s scorecard.">
          <ResponsiveContainer width="100%" height={330}>
            <BarChart data={data.top_reps} layout="vertical" margin={{ left: 8, right: 30 }} barCategoryGap={6}>
              <CartesianGrid horizontal={false} />
              <XAxis type="number" tickFormatter={axisMoney} {...tickProps} />
              <YAxis type="category" dataKey="key" width={130} {...tickProps} />
              <Tooltip content={<ChartTip rows={(d) => [['Won revenue', moneyFull(d.won_revenue)], ['Won deals', num(d.won)], ['Win rate', pct(d.win_rate)]]} />} />
              <Bar dataKey="won_revenue" fill={C.blue} radius={[0, 6, 6, 0]} cursor="pointer" onClick={(d) => openRep(d.key)} animationDuration={800} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
        <Card i={6} title="Deals won vs lost per month" actions={<div className="legend"><span><i style={{ background: C.blue }} />Won</span><span><i style={{ background: C.orange }} />Lost</span></div>}>
          <ResponsiveContainer width="100%" height={330}>
            <BarChart data={data.monthly} margin={{ left: 0, right: 8, top: 8 }} barGap={2}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="period" tickFormatter={monthLabel} {...tickProps} />
              <YAxis width={40} {...tickProps} />
              <Tooltip content={<ChartTip head={(d) => monthLabel(d.period)} rows={(d) => [['Won', num(d.won)], ['Lost', num(d.lost)], ['Win rate', pct(d.win_rate)]]} />} />
              <Bar dataKey="won" fill={C.blue} radius={[4, 4, 0, 0]} />
              <Bar dataKey="lost" fill={C.orange} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <div className="grid grid-2 mt">
        <Card i={7} title="Won revenue by customer sector">
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={data.by_sector} margin={{ left: 0, right: 8, top: 8, bottom: 10 }}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="key" tickFormatter={title} interval={0} angle={-30} textAnchor="end" height={82} {...tickProps} />
              <YAxis tickFormatter={axisMoney} width={56} {...tickProps} />
              <Tooltip content={<ChartTip head={(d) => title(d.key)} rows={(d) => [['Won revenue', moneyFull(d.won_revenue)], ['Share', pct(d.revenue_share)], ['Win rate', pct(d.win_rate)]]} />} />
              <Bar dataKey="won_revenue" radius={[6, 6, 0, 0]} animationDuration={800}>
                {data.by_sector.map((s, idx) => <Cell key={s.key} fill={idx === 0 ? C.blue : '#6da7ec'} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
        <div className="stack">
          <Card i={8} title="Largest open deals" sub="Estimated at list price">
            {data.top_open.map((d) => (
              <div key={d.opportunity_id} className="feed-item" style={{ cursor: 'pointer' }} onClick={() => openDeal(d.opportunity_id)}>
                <StagePill stage={d.deal_stage} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="strong">{d.product} <span className="muted small">· {d.account}</span></div>
                  <div className="muted small">{d.sales_agent} · {d.opportunity_id}</div>
                </div>
                <div style={{ width: 120 }}><Prob value={d.win_probability} /></div>
                <div className="strong right" style={{ width: 64 }}>{money(d.est_open_value)}</div>
              </div>
            ))}
          </Card>
          {data.recent.length > 0 && (
            <Card i={9} title="Recent activity in this app">
              {data.recent.map((d) => (
                <div key={d.opportunity_id} className="feed-item" style={{ cursor: 'pointer' }} onClick={() => openDeal(d.opportunity_id)}>
                  <Gauge size={16} color={C.blue} />
                  <div style={{ flex: 1 }}><span className="strong">{d.opportunity_id}</span> <span className="muted">{d.kind}</span> · {d.product} · {d.account}</div>
                  <StagePill stage={d.deal_stage} />
                </div>
              ))}
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
