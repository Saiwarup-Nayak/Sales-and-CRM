import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Building2, Plus, Save } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { api, useLookups, useMeta } from '../api.js';
import { defaultDate, money, title, todayIso } from '../lib/format.js';
import { useToast } from './overlays.jsx';
import { Alert, Field, Input, Loading, Select, Seg, StagePill } from './ui.jsx';

const NO_ACCOUNT = '';

/** Mutation helper: on success refresh every query and toast; on failure show the validation messages. */
export function useWrite(fn, { success, onDone } = {}) {
  const qc = useQueryClient();
  const toast = useToast();
  const [errors, setErrors] = useState([]);
  const m = useMutation({
    mutationFn: fn,
    onSuccess: (data, vars) => {
      setErrors([]);
      qc.invalidateQueries();
      const s = typeof success === 'function' ? success(data, vars) : success;
      if (s) toast({ kind: 'success', ...s });
      onDone?.(data, vars);
    },
    onError: (e) => {
      setErrors(e.errors || [e.message]);
      toast({ kind: 'error', title: 'Not saved', message: 'Please fix the highlighted problems.' });
    },
  });
  return { ...m, errors, clearErrors: () => setErrors([]) };
}

export function Errors({ errors }) {
  if (!errors?.length) return null;
  return (
    <Alert kind="error" title="Please fix the following">
      <ul>{errors.map((e) => <li key={e}>{e}</li>)}</ul>
    </Alert>
  );
}

/** Forms seed their date defaults from the dataset snapshot, so wait for it before mounting them. */
function withSnapshot(Form) {
  return function WithSnapshot(props) {
    const { data: meta } = useMeta();
    const { data: lk } = useLookups();
    if (!meta?.snapshot || !lk) return <Loading rows={2} h={120} />;
    return <Form {...props} dflt={defaultDate(meta.snapshot)} />;
  };
}

// ---------------------------------------------------------------- new opportunity
export const OpportunityForm = withSnapshot(OpportunityFormInner);
function OpportunityFormInner({ onDone, dflt }) {
  const { data: lk } = useLookups();
  const [f, setF] = useState({ sales_agent: null, product: null, account: NO_ACCOUNT, deal_stage: 'Prospecting',
                               engage_date: dflt, close_date: dflt, close_value: '' });
  const set = (k) => (v) => setF((s) => ({ ...s, [k]: v }));
  const agent = lk?.agents.find((a) => a.sales_agent === f.sales_agent);
  const product = lk?.products.find((p) => p.product === f.product);

  useEffect(() => { // Won deals default to list price (history: median close = 1.0x list price)
    if (f.deal_stage === 'Won' && product && f.close_value === '') setF((s) => ({ ...s, close_value: product.sales_price }));
  }, [f.deal_stage, product, f.close_value]);

  const w = useWrite((body) => api('/opportunities', { method: 'POST', body }), {
    success: (d) => ({ title: `Opportunity ${d.opportunity_id} created`, message: `${d.deal_stage} · ${d.product}` }),
    onDone,
  });
  const submit = (e) => {
    e.preventDefault();
    const s = f.deal_stage;
    w.mutate({
      sales_agent: f.sales_agent, product: f.product, account: f.account || null, deal_stage: s,
      engage_date: s === 'Prospecting' ? null : f.engage_date,
      close_date: ['Won', 'Lost'].includes(s) ? f.close_date : null,
      close_value: s === 'Won' ? Number(f.close_value) : s === 'Lost' ? 0 : null,
    });
  };
  if (!lk) return null;
  return (
    <form className="stack" onSubmit={submit} noValidate>
      <div className="form-grid">
        <Field label="Sales agent *" hint={agent ? `${agent.regional_office} office · manager ${agent.manager}` : null}>
          <Select value={f.sales_agent} onChange={set('sales_agent')} placeholder="Choose a rep" options={lk.agents}
                  getValue={(a) => a.sales_agent} getLabel={(a) => `${a.sales_agent} · ${a.regional_office}`} />
        </Field>
        <Field label="Product *" hint={product ? `Series ${product.series} · list price ${money(product.sales_price)}` : null}>
          <Select value={f.product} onChange={set('product')} placeholder="Choose a product" options={lk.products}
                  getValue={(p) => p.product} getLabel={(p) => `${p.product} · ${money(p.sales_price)}`} />
        </Field>
        <Field label="Account" hint="Required once the deal closes.">
          <Select value={f.account} onChange={(v) => set('account')(v ?? '')} placeholder="(No account yet)" options={lk.accounts} />
        </Field>
      </div>
      <Field label="Stage *">
        <Seg options={['Prospecting', 'Engaging', 'Won', 'Lost']} value={f.deal_stage} onChange={set('deal_stage')} />
      </Field>
      <div className="form-grid">
        {f.deal_stage !== 'Prospecting' && (
          <Field label="Engage date *"><Input type="date" max={todayIso()} value={f.engage_date} onChange={(e) => set('engage_date')(e.target.value)} /></Field>
        )}
        {['Won', 'Lost'].includes(f.deal_stage) && (
          <Field label="Close date *"><Input type="date" max={todayIso()} value={f.close_date} onChange={(e) => set('close_date')(e.target.value)} /></Field>
        )}
        {f.deal_stage === 'Won' && (
          <Field label="Close value ($) *" hint="Defaults to list price.">
            <Input type="number" min="0" step="any" value={f.close_value} onChange={(e) => set('close_value')(e.target.value)} />
          </Field>
        )}
        {f.deal_stage === 'Lost' && <Field label="Close value ($)" hint="Lost deals have no revenue."><Input value="0" disabled /></Field>}
      </div>
      {f.deal_stage === 'Prospecting' && <div className="muted small">Prospecting deals have no engage date yet.</div>}
      <Errors errors={w.errors} />
      <div className="row"><button className="btn primary" disabled={w.isPending}><Plus size={16} /> Create opportunity</button></div>
    </form>
  );
}

// ---------------------------------------------------------------- move a deal through the pipeline
export const StageChangeForm = withSnapshot(StageChangeFormInner);
function StageChangeFormInner({ deal, initialStage, onDone, onCancel, dflt }) {
  const { data: lk } = useLookups();
  const options = deal.deal_stage === 'Prospecting' ? ['Engaging', 'Won', 'Lost'] : ['Won', 'Lost'];
  const [stage, setStage] = useState(options.includes(initialStage) ? initialStage : options[0]);
  const [engage, setEngage] = useState(dflt);
  const [close, setClose] = useState(dflt);
  const [value, setValue] = useState(deal.sales_price ?? '');
  const [account, setAccount] = useState('');
  const needsAccount = ['Won', 'Lost'].includes(stage) && !deal.account_known;

  const w = useWrite((body) => api(`/opportunities/${deal.opportunity_id}`, { method: 'PATCH', body }), {
    success: () => ({ title: `${deal.opportunity_id} moved to ${stage}`, message: `${deal.product} · ${deal.account}` }),
    onDone,
  });
  const submit = (e) => {
    e.preventDefault();
    const body = { deal_stage: stage };
    if (deal.deal_stage === 'Prospecting') body.engage_date = engage;
    if (['Won', 'Lost'].includes(stage)) {
      body.close_date = close;
      body.close_value = stage === 'Won' ? Number(value) : 0;
      if (needsAccount) body.account = account || null;
    }
    w.mutate(body);
  };
  return (
    <form className="stack" onSubmit={submit} noValidate>
      <div className="row ink2 small">Current stage <StagePill stage={deal.deal_stage} /></div>
      <Field label="Move to"><Seg options={options} value={stage} onChange={setStage} /></Field>
      <div className="form-grid">
        {deal.deal_stage === 'Prospecting' && (
          <Field label="Engage date *"><Input type="date" max={todayIso()} value={engage} onChange={(e) => setEngage(e.target.value)} /></Field>
        )}
        {['Won', 'Lost'].includes(stage) && (
          <Field label="Close date *"><Input type="date" max={todayIso()} value={close} onChange={(e) => setClose(e.target.value)} /></Field>
        )}
        {stage === 'Won' && (
          <Field label="Close value ($) *" hint={`List price ${money(deal.sales_price)}`}>
            <Input type="number" min="0" step="any" value={value} onChange={(e) => setValue(e.target.value)} />
          </Field>
        )}
        {needsAccount && lk && (
          <Field label="Account *" hint="Closed deals must be linked to an account.">
            <Select value={account} onChange={(v) => setAccount(v ?? '')} placeholder="Choose an account" options={lk.accounts} />
          </Field>
        )}
      </div>
      <Errors errors={w.errors} />
      <div className="modal-foot" style={{ paddingTop: 4 }}>
        {onCancel && <button type="button" className="btn" onClick={onCancel}>Cancel</button>}
        <button className="btn primary" disabled={w.isPending}><Save size={16} /> Save update</button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------- new account
export function AccountForm({ onDone }) {
  const { data: lk } = useLookups();
  const blank = { account: '', sector: '', office_location: '', year_established: 2000, revenue: 100, employees: 500, subsidiary_of: '' };
  const [f, setF] = useState(blank);
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e?.target ? e.target.value : e }));
  const sectors = useMemo(() => lk?.sectors ?? [], [lk]);
  const w = useWrite((body) => api('/accounts', { method: 'POST', body }), {
    success: (d) => ({ title: `Account ${d.account} created`, message: 'You can now assign deals to it.' }),
    onDone: (d) => { setF(blank); onDone?.(d); },
  });
  const submit = (e) => {
    e.preventDefault();
    w.mutate({ ...f, year_established: Number(f.year_established), revenue: Number(f.revenue), employees: Number(f.employees),
               office_location: f.office_location || null, subsidiary_of: f.subsidiary_of || null });
  };
  if (!lk) return null;
  return (
    <form className="stack" onSubmit={submit} noValidate>
      <div className="form-grid">
        <Field label="Account name *"><Input value={f.account} onChange={set('account')} placeholder="e.g. Northwind Traders" /></Field>
        <Field label="Sector *" hint="Pick one or type a new sector.">
          <Input list="sector-list" value={f.sector} onChange={set('sector')} placeholder="e.g. retail" />
          <datalist id="sector-list">{sectors.map((s) => <option key={s} value={s}>{title(s)}</option>)}</datalist>
        </Field>
        <Field label="HQ country">
          <Input list="loc-list" value={f.office_location} onChange={set('office_location')} placeholder="e.g. United States" />
          <datalist id="loc-list">{lk.locations.map((s) => <option key={s} value={s} />)}</datalist>
        </Field>
      </div>
      <div className="form-grid">
        <Field label="Year established"><Input type="number" min="1800" max={new Date().getFullYear()} value={f.year_established} onChange={set('year_established')} /></Field>
        <Field label="Annual revenue ($M)"><Input type="number" min="0" step="10" value={f.revenue} onChange={set('revenue')} /></Field>
        <Field label="Employees"><Input type="number" min="0" step="10" value={f.employees} onChange={set('employees')} /></Field>
        <Field label="Parent company">
          <Select value={f.subsidiary_of} onChange={(v) => set('subsidiary_of')(v ?? '')} placeholder="None" options={lk.accounts} />
        </Field>
      </div>
      <Errors errors={w.errors} />
      <div className="row"><button className="btn primary" disabled={w.isPending}><Building2 size={16} /> Create account</button></div>
    </form>
  );
}
