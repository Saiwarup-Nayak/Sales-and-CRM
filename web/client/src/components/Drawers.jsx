import { ArrowRightLeft, Trash2 } from 'lucide-react';
import { createContext, useContext, useState } from 'react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import { api, useApi } from '../api.js';
import { axisMoney, date, money, moneyFull, monthLabel, pct, title } from '../lib/format.js';
import { C, OUTCOME_COLORS } from '../lib/palette.js';
import { StageChangeForm, useWrite } from './forms.jsx';
import { Drawer } from './overlays.jsx';
import { Card, ChartTip, DetailGrid, KpiCard, Loading, Prob, StagePill } from './ui.jsx';

// Global "open a record" context so tables, the pipeline board and the command palette share drawers.
const Ctx = createContext(null);
export const useDrawers = () => useContext(Ctx);

export function DrawerProvider({ children }) {
  const [state, setState] = useState({ deal: null, account: null, rep: null });
  const api_ = {
    openDeal: (id) => setState({ deal: id, account: null, rep: null }),
    openAccount: (name) => setState({ deal: null, account: name, rep: null }),
    openRep: (name) => setState({ deal: null, account: null, rep: name }),
    close: () => setState({ deal: null, account: null, rep: null }),
  };
  return (
    <Ctx.Provider value={api_}>
      {children}
      <DealDrawer id={state.deal} onClose={api_.close} />
      <AccountDrawer name={state.account} onClose={api_.close} />
      <RepDrawer name={state.rep} onClose={api_.close} />
    </Ctx.Provider>
  );
}

// ---------------------------------------------------------------- deal
function DealDrawer({ id, onClose }) {
  const { data: d, isLoading } = useApi(['deal', id], `/opportunities/${id}`, { enabled: !!id, placeholderData: undefined });
  const [moving, setMoving] = useState(false);
  const del = useWrite(() => api(`/opportunities/${id}`, { method: 'DELETE' }), {
    success: { title: `Opportunity ${id} deleted` }, onDone: onClose,
  });
  const close = () => { setMoving(false); onClose(); };
  return (
    <Drawer open={!!id} onClose={close} title={id}
            sub={d ? `${d.product} for ${d.account} · ${d.sales_agent}` : ' '}
            actions={d && <StagePill stage={d.deal_stage} />}>
      {isLoading || !d ? <Loading /> : (
        <div className="stack">
          {d.is_open && !moving && (
            <div className="row">
              <button className="btn primary" onClick={() => setMoving(true)}><ArrowRightLeft size={16} /> Move stage</button>
              {d.source === 'user' && (
                <button className="btn danger" onClick={() => window.confirm('Delete this opportunity? This cannot be undone.') && del.mutate()}>
                  <Trash2 size={16} /> Delete
                </button>
              )}
            </div>
          )}
          {moving && (
            <Card float={false} title="Move this deal">
              <StageChangeForm deal={d} onDone={() => setMoving(false)} onCancel={() => setMoving(false)} />
            </Card>
          )}
          <DetailGrid items={[
            ['Account', d.account], ['Sector', title(d.sector)],
            ['Product', `${d.product} (${d.series})`], ['List price', moneyFull(d.sales_price)],
            ['Sales rep', d.sales_agent], ['Manager', d.manager], ['Office', d.regional_office],
            ['Engaged', date(d.engage_date)], ['Closed', date(d.close_date)],
            ['Close value', d.is_closed ? moneyFull(d.close_value) : '–'],
            ['Sales cycle', d.sales_cycle_days != null ? `${d.sales_cycle_days} days` : '–'],
            ['Days open', d.open_age_days != null ? d.open_age_days : '–'],
            ['Source', d.source === 'user' ? 'Added in this app' : 'Original dataset'],
            ['Last updated', d.updated_at ? date(d.updated_at) : '–'],
          ]} />
          {d.is_open && (
            <Card float={false} title="Win probability" sub="Model estimate for an open deal">
              <Prob value={d.win_probability} />
              <div className="muted small" style={{ marginTop: 8 }}>
                {d.win_probability == null ? 'Not scored yet. Scores refresh automatically a few seconds after changes.'
                  : 'The model is no better than chance on this dataset (test ROC-AUC ≈ 0.50), so treat this as indicative only.'}
              </div>
            </Card>
          )}
        </div>
      )}
    </Drawer>
  );
}

// ---------------------------------------------------------------- account
function AccountDrawer({ name, onClose }) {
  const { openDeal } = useDrawers();
  const { data, isLoading } = useApi(['account', name], `/accounts/${encodeURIComponent(name ?? '')}`, { enabled: !!name, placeholderData: undefined });
  const a = data?.account;
  return (
    <Drawer open={!!name} onClose={onClose} title={name}
            sub={a ? `${title(a.sector)} · ${a.office_location ?? '–'}${a.subsidiary_of ? ` · subsidiary of ${a.subsidiary_of}` : ''}` : ' '}>
      {isLoading || !data ? <Loading /> : (
        <div className="stack">
          <div className="grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
            <KpiCard label="Won revenue" value={data.kpis.won_revenue} format={money} />
            <KpiCard label="Win rate" value={data.kpis.win_rate} format={(v) => pct(v)} i={1} />
            <KpiCard label="Deals" value={data.kpis.total_opportunities} format={(v) => Math.round(v)} i={2} />
          </div>
          <DetailGrid items={[['Employees', a.employees?.toLocaleString()], ['Revenue', a.revenue != null ? `$${a.revenue.toLocaleString()}M` : '–'],
                              ['Founded', a.year_established], ['Source', a.source === 'user' ? 'Added in this app' : 'Original dataset']]} />
          {data.products.length > 0 && (
            <Card float={false} title="Deals by product and outcome">
              <ResponsiveContainer width="100%" height={Math.max(160, data.products.length * 34 + 40)}>
                <BarChart data={data.products} layout="vertical" margin={{ left: 10, right: 10 }} barCategoryGap={8}>
                  <CartesianGrid horizontal={false} />
                  <XAxis type="number" allowDecimals={false} tickLine={false} axisLine={false} />
                  <YAxis type="category" dataKey="product" width={100} tickLine={false} axisLine={false} />
                  <Tooltip content={<ChartTip rows={(d) => [['Won', d.won], ['Lost', d.lost], ['Open', d.open]]} />} />
                  {['Won', 'Lost', 'Open'].map((k) => (
                    <Bar key={k} dataKey={k.toLowerCase()} stackId="a" fill={OUTCOME_COLORS[k]} stroke="#fff" strokeWidth={2} name={k} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
              <div className="legend">{['Won', 'Lost', 'Open'].map((k) => <span key={k}><i style={{ background: OUTCOME_COLORS[k] }} />{k}</span>)}</div>
            </Card>
          )}
          <Card float={false} title={`Deals (${data.deals.length})`}>
            {data.deals.slice(0, 40).map((d) => (
              <div key={d.opportunity_id} className="feed-item" style={{ cursor: 'pointer' }} onClick={() => openDeal(d.opportunity_id)}>
                <StagePill stage={d.deal_stage} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="strong">{d.product} <span className="muted small">· {d.opportunity_id}</span></div>
                  <div className="muted small">{d.sales_agent} · engaged {date(d.engage_date)}</div>
                </div>
                <div className="right strong">{d.is_won ? money(d.close_value) : d.is_open ? <span className="muted">{money(d.est_open_value)} est.</span> : '–'}</div>
              </div>
            ))}
            {data.deals.length > 40 && <div className="muted small" style={{ paddingTop: 8 }}>Showing the 40 most recent.</div>}
          </Card>
        </div>
      )}
    </Drawer>
  );
}

// ---------------------------------------------------------------- rep
function RepDrawer({ name, onClose }) {
  const { data, isLoading } = useApi(['rep', name], `/team/${encodeURIComponent(name ?? '')}`, { enabled: !!name, placeholderData: undefined });
  return (
    <Drawer open={!!name} onClose={onClose} title={name} sub={data ? `${data.regional_office} office · reports to ${data.manager}` : ' '}>
      {isLoading || !data ? <Loading /> : (
        <div className="stack">
          <div className="grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
            <KpiCard label="Won revenue" value={data.kpis.won_revenue} format={money} />
            <KpiCard label="Win rate" value={data.kpis.win_rate} format={(v) => pct(v)} i={1} />
            <KpiCard label="Open deals" value={data.kpis.open_opportunities} format={(v) => Math.round(v)} i={2} />
          </div>
          <Card float={false} title="Monthly won revenue">
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={data.monthly} margin={{ left: 0, right: 6 }}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="period" tickFormatter={monthLabel} tickLine={false} axisLine={false} />
                <YAxis tickFormatter={axisMoney} tickLine={false} axisLine={false} width={52} />
                <Tooltip content={<ChartTip head={(d) => monthLabel(d.period)} rows={(d) => [['Won revenue', moneyFull(d.won_revenue)], ['Won / lost', `${d.won} / ${d.lost}`]]} />} />
                <Bar dataKey="won_revenue" fill={C.blue} radius={[5, 5, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
          <Card float={false} title="By product">
            {data.products.map((p) => (
              <div key={p.key} className="feed-item">
                <div style={{ width: 110 }} className="strong">{p.key}</div>
                <div style={{ flex: 1 }}><div className="bar-inline"><div style={{ width: `${(p.revenue_share ?? 0) * 100}%` }} /></div></div>
                <div className="right" style={{ width: 150 }}>{money(p.won_revenue)} <span className="muted small">· {pct(p.win_rate)}</span></div>
              </div>
            ))}
          </Card>
        </div>
      )}
    </Drawer>
  );
}
