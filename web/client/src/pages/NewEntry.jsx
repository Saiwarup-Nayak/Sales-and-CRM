import { Building2, Handshake, History, RotateCcw, Trash2 } from 'lucide-react';
import { useState } from 'react';

import { api, useApi } from '../api.js';
import { useDrawers } from '../components/Drawers.jsx';
import DataTable from '../components/DataTable.jsx';
import { AccountForm, Errors, OpportunityForm, useWrite } from '../components/forms.jsx';
import { Alert, Card, Field, Input, PageHead, Seg, StagePill } from '../components/ui.jsx';
import { date, moneyFull, title } from '../lib/format.js';

const TABS = { opp: 'New opportunity', account: 'New account', mine: 'My entries' };
const ICONS = { opp: Handshake, account: Building2, mine: History };

export default function NewEntry() {
  const [tab, setTab] = useState('opp');
  return (
    <>
      <PageHead title="Add / my entries" sub="Create records and manage what you've added. Every entry is validated before it's saved." />
      <div className="tabs">
        <Seg options={Object.keys(TABS)} value={tab} onChange={setTab}
             getLabel={(k) => { const I = ICONS[k]; return <span className="row" style={{ gap: 6 }}><I size={15} />{TABS[k]}</span>; }} />
      </div>
      {tab === 'opp' && (
        <div className="grid grid-3-2">
          <Card title="New opportunity" sub="The form adapts to the stage you choose.">
            <OpportunityForm />
          </Card>
          <Card i={1} title="Rules every deal must follow" float={false}>
            <ul className="ink2" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.9 }}>
              <li><StagePill stage="Prospecting" /> has no engage date, close date or value.</li>
              <li><StagePill stage="Engaging" /> needs an engage date.</li>
              <li><StagePill stage="Won" /> needs a close date, an account and a value above $0.</li>
              <li><StagePill stage="Lost" /> needs a close date and an account. The value is always $0.</li>
              <li>Dates must be in order and can’t be in the future.</li>
            </ul>
            <div className="muted small" style={{ marginTop: 12 }}>Dates default to the last date in the sample data, so new deals line up with the history on the charts.
              New open deals get a win probability a few seconds after saving.</div>
          </Card>
        </div>
      )}
      {tab === 'account' && <Card title="New account" sub="Create a customer company, then assign deals to it."><AccountForm /></Card>}
      {tab === 'mine' && <MyEntries />}
    </>
  );
}

function MyEntries() {
  const { data } = useApi('entries', '/entries');
  const { openDeal, openAccount } = useDrawers();
  const delOpp = useWrite((id) => api(`/opportunities/${id}`, { method: 'DELETE' }), { success: (_, id) => ({ title: `Opportunity ${id} deleted` }) });
  const delAcc = useWrite((n) => api(`/accounts/${encodeURIComponent(n)}`, { method: 'DELETE' }), { success: (_, n) => ({ title: `Account ${n} deleted` }) });
  const [confirm, setConfirm] = useState('');
  const reset = useWrite(() => api('/jobs/reset', { method: 'POST', body: { confirm } }), {
    success: { title: 'CRM reset to the original GitHub data' }, onDone: () => setConfirm(''),
  });
  const stop = (fn) => (e) => { e.stopPropagation(); fn(); };

  const oppCols = [
    { key: 'opportunity_id', label: 'ID', render: (r) => <span className="strong">{r.opportunity_id}</span> },
    { key: 'deal_stage', label: 'Stage', render: (r) => <StagePill stage={r.deal_stage} /> },
    { key: 'product', label: 'Product' }, { key: 'account', label: 'Account' }, { key: 'sales_agent', label: 'Rep' },
    { key: 'close_value', label: 'Value', num: true, render: (r) => moneyFull(r.close_value) },
    { key: 'source', label: 'Change', render: (r) => (r.source === 'user' ? <span className="tag user">created</span> : <span className="tag">updated</span>) },
    { key: 'at', label: 'When', render: (r) => date(r.updated_at || r.created_at) },
    { key: 'x', label: '', render: (r) => (r.source === 'user' ? (
      <button className="btn sm danger" onClick={stop(() => window.confirm(`Delete ${r.opportunity_id}?`) && delOpp.mutate(r.opportunity_id))}><Trash2 size={14} /></button>) : null) },
  ];
  const accCols = [
    { key: 'account', label: 'Account', render: (r) => <span className="strong">{r.account}</span> },
    { key: 'sector', label: 'Sector', render: (r) => title(r.sector) }, { key: 'office_location', label: 'HQ' },
    { key: 'employees', label: 'Employees', num: true }, { key: 'at', label: 'Created', render: (r) => date(r.created_at) },
    { key: 'x', label: '', render: (r) => <button className="btn sm danger" onClick={stop(() => window.confirm(`Delete ${r.account}?`) && delAcc.mutate(r.account))}><Trash2 size={14} /></button> },
  ];
  return (
    <div className="stack">
      <Card title={`Opportunities created or updated here (${data?.opportunities.length ?? 0})`} sub="Updated deals from the original data can't be deleted, only deals you created.">
        <DataTable columns={oppCols} rows={data?.opportunities} loading={!data} rowKey={(r) => r.opportunity_id} onRowClick={(r) => openDeal(r.opportunity_id)} maxHeight={360} />
        <Errors errors={delOpp.errors} />
      </Card>
      <Card i={1} title={`Accounts created here (${data?.accounts.length ?? 0})`} sub="An account can only be deleted once it has no deals.">
        <DataTable columns={accCols} rows={data?.accounts} loading={!data} rowKey={(r) => r.account} onRowClick={(r) => openAccount(r.account)} maxHeight={300} />
        <Errors errors={delAcc.errors} />
      </Card>
      <Card i={2} float={false} title="Reset CRM" sub="Re-download the dataset from GitHub and discard every entry and update made here.">
        <div className="stack">
          <Alert kind="warn">This can’t be undone. Type <b>RESET</b> to confirm.</Alert>
          <div className="row" style={{ alignItems: 'flex-end' }}>
            <div style={{ width: 220 }}><Field label="Confirmation"><Input value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="RESET" /></Field></div>
            <button className="btn danger solid" disabled={confirm !== 'RESET' || reset.isPending} onClick={() => reset.mutate()}>
              <RotateCcw size={16} /> {reset.isPending ? 'Resetting…' : 'Reset CRM'}
            </button>
          </div>
          <Errors errors={reset.errors} />
        </div>
      </Card>
    </div>
  );
}
