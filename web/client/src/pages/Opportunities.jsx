import { Download, Search } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { qs, useApi, useLookups } from '../api.js';
import { useDrawers } from '../components/Drawers.jsx';
import DataTable from '../components/DataTable.jsx';
import { Card, Chips, KpiCard, PageHead, Prob, SearchInput, Select, StagePill, useDebounced } from '../components/ui.jsx';
import { date, money, moneyFull, num, pct } from '../lib/format.js';

const STAGES = ['Prospecting', 'Engaging', 'Won', 'Lost'];

export default function Opportunities() {
  const [params] = useSearchParams();
  const { data: lk } = useLookups();
  const { openDeal } = useDrawers();
  const [q, setQ] = useState('');
  const [stages, setStages] = useState(() => (params.get('stages') ? params.get('stages').split(',') : []));
  const [rep, setRep] = useState(null);
  const [product, setProduct] = useState(null);
  const [office, setOffice] = useState(null);
  const [sort, setSort] = useState(null);
  const [page, setPage] = useState(1);
  const dq = useDebounced(q);
  const pageSize = 25;

  useEffect(() => setPage(1), [dq, stages, rep, product, office, sort]);
  const filters = { q: dq, stages, rep, product, office };
  const { data, isFetching } = useApi(['opps', filters, sort, page],
    `/opportunities${qs({ ...filters, sort: sort?.key, dir: sort?.dir, page, pageSize })}`);
  const s = data?.summary;

  const exportCsv = async () => {
    const all = await fetch(`/api/opportunities${qs({ ...filters, sort: sort?.key, dir: sort?.dir, page: 1, pageSize: 'all' })}`).then((r) => r.json());
    const cols = ['opportunity_id', 'deal_stage', 'account', 'product', 'sales_agent', 'regional_office', 'engage_date', 'close_date', 'close_value', 'est_open_value', 'win_probability'];
    const csv = [cols.join(','), ...all.rows.map((r) => cols.map((c) => JSON.stringify(r[c] ?? '')).join(','))].join('\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    a.download = 'opportunities.csv';
    a.click();
  };

  const columns = [
    { key: 'opportunity_id', label: 'ID', sortable: true, render: (r) => <span className="strong">{r.opportunity_id}</span> },
    { key: 'deal_stage', label: 'Stage', sortable: true, render: (r) => <StagePill stage={r.deal_stage} /> },
    { key: 'account', label: 'Account', sortable: true },
    { key: 'product', label: 'Product', sortable: true },
    { key: 'sales_agent', label: 'Rep', sortable: true },
    { key: 'regional_office', label: 'Office', sortable: true },
    { key: 'engage_date', label: 'Engaged', sortable: true, render: (r) => date(r.engage_date) },
    { key: 'close_date', label: 'Closed', sortable: true, render: (r) => date(r.close_date) },
    { key: 'close_value', label: 'Close value', sortable: true, num: true, render: (r) => (r.is_closed ? moneyFull(r.close_value) : '–') },
    { key: 'est_open_value', label: 'Est. value', sortable: true, num: true, render: (r) => (r.is_open ? moneyFull(r.est_open_value) : '–') },
    { key: 'win_probability', label: 'Win prob.', sortable: true, render: (r) => (r.is_open ? <Prob value={r.win_probability} /> : '–') },
    { key: 'source', label: '', render: (r) => (r.source === 'user' ? <span className="tag user">added</span> : null) },
  ];

  return (
    <>
      <PageHead title="Opportunities" sub="Every deal in the pipeline. Click a row to open it.">
        <button className="btn" onClick={exportCsv}><Download size={16} /> Export CSV</button>
      </PageHead>

      <Card float={false} style={{ marginBottom: 16, padding: '14px 16px' }}>
        <div className="row" style={{ gap: 12 }}>
          <SearchInput value={q} onChange={setQ} placeholder="Search ID, account, rep, product, sector…" icon={Search} />
          <Chips options={STAGES} value={stages} onChange={setStages} />
          <div style={{ width: 190 }}><Select value={rep} onChange={setRep} placeholder="All reps" options={(lk?.agents ?? []).map((a) => a.sales_agent)} /></div>
          <div style={{ width: 160 }}><Select value={product} onChange={setProduct} placeholder="All products" options={(lk?.products ?? []).map((p) => p.product)} /></div>
          <div style={{ width: 140 }}><Select value={office} onChange={setOffice} placeholder="All offices" options={lk?.offices ?? []} /></div>
        </div>
      </Card>

      <div className="grid grid-kpi">
        <KpiCard i={0} label="Deals shown" value={data?.total} format={(v) => num(Math.round(v))} />
        <KpiCard i={1} label="Open" value={s?.open_opportunities} format={(v) => num(Math.round(v))} sub={s ? `${money(s.open_pipeline_est_value)} est. value` : ''} />
        <KpiCard i={2} label="Won" value={s?.won_deals} format={(v) => num(Math.round(v))} sub={s ? `${money(s.won_revenue)} revenue` : ''} />
        <KpiCard i={3} label="Win rate" value={s?.win_rate} format={(v) => pct(v)} sub={s ? `${num(s.closed_opportunities)} closed` : ''} />
      </div>

      <Card float={false} style={{ opacity: isFetching ? 0.8 : 1, transition: 'opacity .2s' }}>
        <DataTable columns={columns} rows={data?.rows} loading={!data} onRowClick={(r) => openDeal(r.opportunity_id)}
                   rowKey={(r) => r.opportunity_id} sort={sort} onSort={setSort}
                   page={page} pageSize={pageSize} total={data?.total ?? 0} onPage={setPage} />
      </Card>
    </>
  );
}
