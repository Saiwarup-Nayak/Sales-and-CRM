import { Building2, Search } from 'lucide-react';
import { useMemo, useState } from 'react';

import { useApi } from '../api.js';
import { useDrawers } from '../components/Drawers.jsx';
import DataTable from '../components/DataTable.jsx';
import { Card, Chips, KpiCard, Loading, PageHead, SearchInput, Seg } from '../components/ui.jsx';
import { money, moneyFull, num, pct, title } from '../lib/format.js';

export default function Accounts() {
  const { data } = useApi('accounts', '/accounts');
  const { openAccount } = useDrawers();
  const [q, setQ] = useState('');
  const [sectors, setSectors] = useState([]);
  const [sort, setSort] = useState({ key: 'won_revenue', dir: 'desc' });
  const [view, setView] = useState('cards');

  const rows = useMemo(() => {
    if (!data) return [];
    const ql = q.toLowerCase();
    const out = data.accounts.filter((a) => (!sectors.length || sectors.includes(a.sector))
      && (!ql || [a.account, a.office_location, a.subsidiary_of, a.sector].some((v) => v && v.toLowerCase().includes(ql))));
    const d = sort.dir === 'asc' ? 1 : -1;
    return out.sort((a, b) => ((a[sort.key] ?? -Infinity) > (b[sort.key] ?? -Infinity) ? d : -d));
  }, [data, q, sectors, sort]);

  if (!data) return <><PageHead title="Accounts" /><Loading rows={3} h={360} /></>;
  const allSectors = [...new Set(data.accounts.map((a) => a.sector))].sort();
  const totalRev = rows.reduce((s, a) => s + a.won_revenue, 0);
  const maxRev = Math.max(...rows.map((a) => a.won_revenue), 1);

  const columns = [
    { key: 'account', label: 'Account', sortable: true, render: (a) => <span className="strong">{a.account}</span> },
    { key: 'sector', label: 'Sector', sortable: true, render: (a) => title(a.sector) },
    { key: 'office_location', label: 'HQ', sortable: true },
    { key: 'employees', label: 'Employees', num: true, sortable: true, render: (a) => num(a.employees) },
    { key: 'revenue', label: 'Revenue ($M)', num: true, sortable: true, render: (a) => num(a.revenue, 1) },
    { key: 'opportunities', label: 'Deals', num: true, sortable: true },
    { key: 'win_rate', label: 'Win rate', num: true, sortable: true, render: (a) => pct(a.win_rate) },
    { key: 'won_revenue', label: 'Won revenue', num: true, sortable: true, render: (a) => moneyFull(a.won_revenue) },
    { key: 'open_pipeline_est_value', label: 'Open (est.)', num: true, sortable: true, render: (a) => moneyFull(a.open_pipeline_est_value) },
    { key: 'source', label: '', render: (a) => (a.source === 'user' ? <span className="tag user">added</span> : null) },
  ];

  return (
    <>
      <PageHead title="Accounts" sub={`${data.accounts.length} customer companies. Click one to open it.`}>
        <Seg options={['cards', 'table']} value={view} onChange={setView} getLabel={title} />
      </PageHead>

      <div className="grid grid-kpi">
        <KpiCard i={0} label="Accounts" value={rows.length} format={(v) => Math.round(v)} icon={Building2} sub={`${new Set(rows.map((a) => a.sector)).size} sectors`} />
        <KpiCard i={1} label="Won revenue" value={totalRev} format={money} sub={`${num(rows.reduce((s, a) => s + a.won, 0))} won deals`} />
        <KpiCard i={2} label="Top account" value={rows[0]?.account ?? '–'} sub={rows[0] ? money(rows[0].won_revenue) : ''} />
        <KpiCard i={3} label="Unassigned deals" value={data.unassigned} format={(v) => num(Math.round(v))} sub="open deals with no account yet" />
      </div>

      <Card float={false} style={{ marginBottom: 16, padding: '14px 16px' }}>
        <div className="row" style={{ gap: 12 }}>
          <SearchInput value={q} onChange={setQ} placeholder="Search name, country, parent company…" icon={Search} />
          <Chips options={allSectors} value={sectors} onChange={setSectors} />
        </div>
      </Card>

      {view === 'table' ? (
        <Card float={false}>
          <DataTable columns={columns} rows={rows} onRowClick={(a) => openAccount(a.account)} rowKey={(a) => a.account}
                     sort={sort} onSort={setSort} maxHeight={620} />
        </Card>
      ) : (
        <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))' }}>
          {rows.map((a, i) => (
            <Card key={a.account} i={Math.min(i, 12)} onClick={() => openAccount(a.account)} style={{ cursor: 'pointer' }}>
              <div className="row" style={{ flexWrap: 'nowrap' }}>
                <div className="avatar">{a.account.slice(0, 2).toUpperCase()}</div>
                <div style={{ minWidth: 0 }}>
                  <div className="strong" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.account}</div>
                  <div className="muted small">{title(a.sector)} · {a.office_location ?? '–'}</div>
                </div>
                {a.source === 'user' && <span className="tag user" style={{ marginLeft: 'auto' }}>added</span>}
              </div>
              <div className="row" style={{ justifyContent: 'space-between', marginTop: 14 }}>
                <div><div className="muted small">Won revenue</div><div className="strong" style={{ fontSize: 18 }}>{money(a.won_revenue)}</div></div>
                <div className="right"><div className="muted small">Win rate</div><div className="strong" style={{ fontSize: 18 }}>{pct(a.win_rate, 0)}</div></div>
              </div>
              <div className="bar-inline" style={{ marginTop: 10 }}><div style={{ width: `${(a.won_revenue / maxRev) * 100}%` }} /></div>
              <div className="muted small" style={{ marginTop: 8 }}>{a.opportunities} deals · {a.open} open · {num(a.employees)} employees</div>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
