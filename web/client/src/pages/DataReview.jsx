import { CheckCircle2, AlertTriangle, XCircle, Search } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import { qs, useApi } from '../api.js';
import DataTable from '../components/DataTable.jsx';
import { Card, ChartTip, Field, KpiCard, Loading, PageHead, SearchInput, Seg, Select, useDebounced } from '../components/ui.jsx';
import { money, num, pct } from '../lib/format.js';
import { C, rampColor } from '../lib/palette.js';

const TABS = ['Dataset', 'Cleaning', 'Missing values', 'Normalisation', 'Outliers', 'Encoding', 'Features', 'Final dataset'];

export default function DataReview() {
  const { data: r } = useApi('review', '/review', { staleTime: Infinity });
  const [tab, setTab] = useState('Dataset');
  if (!r) return <><PageHead title="Data review" /><Loading rows={3} h={360} /></>;
  const s = r.summary;
  return (
    <>
      <PageHead title="Data review" sub="The original GitHub dataset and every preprocessing step: what changed, how many rows, and why." />
      <div className="grid grid-kpi">
        <KpiCard i={0} label="Opportunities" value={s.raw_rows} format={(v) => num(Math.round(v))} sub={`${num(s.clean_rows)} after cleaning`} />
        <KpiCard i={1} label="Values corrected" value={r.cleaning_log.filter((l) => /map|spelling|Title|strip/.test(l.technique)).reduce((a, l) => a + l['rows affected'], 0)} format={(v) => num(Math.round(v))} sub="names standardised" />
        <KpiCard i={2} label="Missing cells (raw join)" value={s.missing_cells_raw} format={(v) => num(Math.round(v))} sub="mostly structural" />
        <KpiCard i={3} label="Integrity checks" value={s.checks} format={(v) => Math.round(v)} sub={`${s.checks_attention} need attention`} />
        <KpiCard i={4} label="Columns" value={s.clean_columns} format={(v) => Math.round(v)} sub={`${s.raw_columns} raw + ${s.clean_columns - s.raw_columns} engineered`} />
      </div>
      <div className="tabs"><Seg options={TABS} value={tab} onChange={setTab} /></div>
      {tab === 'Dataset' && <TableBrowser initial="raw_joined"
                                         productFix={r.cleaning_log.find((l) => l.column === 'product')} />}
      {tab === 'Cleaning' && <Cleaning r={r} />}
      {tab === 'Missing values' && <Missing r={r} />}
      {tab === 'Normalisation' && <Normalisation r={r} />}
      {tab === 'Outliers' && <Outliers r={r} />}
      {tab === 'Encoding' && <Encoding r={r} />}
      {tab === 'Features' && <Features r={r} />}
      {tab === 'Final dataset' && <TableBrowser initial="clean" lock />}
    </>
  );
}

// ---------------------------------------------------------------- dataset browser
const TABLES = { raw_joined: 'Joined (raw keys)', sales_pipeline: 'sales_pipeline', accounts: 'accounts', products: 'products',
                 sales_teams: 'sales_teams', data_dictionary: 'data_dictionary', clean: 'Cleaned dataset' };

function TableBrowser({ initial, lock, productFix }) {
  const [name, setName] = useState(initial);
  const [q, setQ] = useState('');
  const [page, setPage] = useState(1);
  const dq = useDebounced(q);
  const { data } = useApi(['rtable', name, dq, page], `/review/table/${name}${qs({ q: dq, page, pageSize: 50 })}`);
  const columns = (data?.columns ?? []).map((c) => ({ key: c, label: c, render: (row) => fmtCell(row[c]) }));
  return (
    <Card float={false} title={lock ? 'Final preprocessed dataset' : 'Complete dataset as published'}
          sub={data ? `${num(data.total)} of ${num(data.all)} rows × ${data.columns.length} columns` : ' '}>
      <div className="row" style={{ marginBottom: 12 }}>
        {!lock && <div style={{ width: 220 }}><Select value={name} onChange={(v) => { setName(v || initial); setPage(1); }}
                                                      options={Object.keys(TABLES).filter((k) => k !== 'clean')} getLabel={(k) => TABLES[k]} /></div>}
        <SearchInput value={q} onChange={(v) => { setQ(v); setPage(1); }} placeholder="Search all columns…" icon={Search} />
      </div>
      {name === 'raw_joined' && productFix?.['rows affected'] > 0 && (
        <div className="alert info small" style={{ marginBottom: 12 }}>Raw tables joined on their original keys. {num(productFix['rows affected'])} deals show
          empty product details because the pipeline says “{productFix['example before']}” while products.csv says “{productFix['example after']}”. The Cleaning tab shows the fix.</div>
      )}
      <DataTable columns={columns} rows={data?.rows} loading={!data} page={page} pageSize={50} total={data?.total ?? 0} onPage={setPage} maxHeight={520} />
    </Card>
  );
}
const fmtCell = (v) => (v === null || v === undefined ? <span className="muted">null</span> : typeof v === 'boolean' ? String(v) : typeof v === 'number' ? num(v, 2) : String(v));

// ---------------------------------------------------------------- cleaning
const STATUS = { pass: [CheckCircle2, '#0ca30c', 'pass'], warn: [AlertTriangle, '#c98500', 'warn'], fail: [XCircle, '#d03b3b', 'fail'] };

function Cleaning({ r }) {
  const active = r.cleaning_log.filter((l) => l['rows affected'] > 0).map((l) => ({ ...l, label: `${l.step} · ${l.column}` }));
  return (
    <div className="stack">
      <Card title="What was cleaned, and how much" sub="Rules with zero hits still ran on every row">
        <ResponsiveContainer width="100%" height={60 + active.length * 38}>
          <BarChart data={active} layout="vertical" margin={{ left: 8, right: 40 }} barCategoryGap={8}>
            <CartesianGrid horizontal={false} />
            <XAxis type="number" tickLine={false} axisLine={false} />
            <YAxis type="category" dataKey="label" width={260} tickLine={false} axisLine={false} />
            <Tooltip content={<ChartTip head={(d) => d.label} rows={(d) => [['Rows affected', num(d['rows affected'])], ['Technique', d.technique]]} />} />
            <Bar dataKey="rows affected" fill={C.blue} radius={[0, 6, 6, 0]} label={{ position: 'right', fill: C.ink2, fontSize: 12, formatter: (v) => num(v) }} />
          </BarChart>
        </ResponsiveContainer>
      </Card>
      <Card i={1} float={false} title="Cleaning log">
        <DataTable rows={r.cleaning_log} maxHeight={480} columns={[
          { key: 'step', label: 'Step', render: (l) => <span className="strong">{l.step}</span> }, { key: 'table', label: 'Table' },
          { key: 'column', label: 'Column' }, { key: 'technique', label: 'Technique' },
          { key: 'rows affected', label: 'Rows', num: true, render: (l) => num(l['rows affected']) },
          { key: 'example before', label: 'Before' }, { key: 'example after', label: 'After' },
          { key: 'why', label: 'Why', render: (l) => <span className="ink2" style={{ whiteSpace: 'normal', display: 'block', minWidth: 260 }}>{l.why}</span> },
        ]} />
      </Card>
      <div className="grid grid-2">
        <Card i={2} title="Integrity checks" sub={`${r.integrity.length} checks on structure, rules and joins`}>
          <div style={{ maxHeight: 420, overflow: 'auto' }}>
            {r.integrity.map((c) => {
              const [Icon, color, label] = STATUS[c.status];
              return (
                <div key={c.check} className="feed-item" style={{ alignItems: 'flex-start' }}>
                  <Icon size={17} color={color} style={{ flex: 'none', marginTop: 2 }} />
                  <div style={{ flex: 1 }}><div className="strong small">{c.check}</div><div className="muted small">{c.detail}</div></div>
                  <span className="tag">{label}</span>
                </div>
              );
            })}
          </div>
        </Card>
        <div className="stack">
          <Card i={3} title="Sector typo fix">
            <DataTable rows={r.sector_fix} columns={[{ key: 'sector', label: 'Sector' }, { key: 'raw', label: 'Raw', num: true }, { key: 'clean', label: 'Clean', num: true }]} maxHeight={300} />
          </Card>
          <Card i={4} title="Type conversions">
            <DataTable rows={r.dtypes.filter((d) => d.changed)} columns={[{ key: 'column', label: 'Column' }, { key: 'raw dtype', label: 'Raw' }, { key: 'clean dtype', label: 'Clean' }]} />
          </Card>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- missing values
function Missing({ r }) {
  const rows = r.missing.filter((m) => m['missing (raw)'] > 0 || m['missing (clean)'] > 0);
  const cols = ['account', 'engage_date', 'close_date', 'close_value'];
  return (
    <div className="stack">
      <Card title="Share of rows missing, raw vs clean" actions={<div className="legend"><span><i style={{ background: C.blue }} />Raw</span><span><i style={{ background: C.orange }} />After cleaning</span></div>}>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={rows} margin={{ left: 0, right: 8, top: 8, bottom: 30 }} barGap={2}>
            <CartesianGrid vertical={false} />
            <XAxis dataKey="column" interval={0} angle={-30} textAnchor="end" height={60} tickLine={false} axisLine={false} />
            <YAxis tickFormatter={(v) => `${v}%`} width={44} tickLine={false} axisLine={false} />
            <Tooltip content={<ChartTip head={(d) => d.column} rows={(d) => [['Raw', `${d['% raw'].toFixed(1)}%`], ['Clean', `${d['% clean'].toFixed(1)}%`], ['Treatment', d.treatment]]} />} />
            <Bar dataKey="% raw" fill={C.blue} radius={[4, 4, 0, 0]} />
            <Bar dataKey="% clean" fill={C.orange} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </Card>
      <div className="grid grid-2-3">
        <Card i={1} title="Missingness by deal stage" sub="The gaps follow from each deal's stage, so they are structural, not random">
          <div style={{ display: 'grid', gridTemplateColumns: `130px repeat(${cols.length}, 1fr)`, gap: 4 }}>
            <div />{cols.map((c) => <div key={c} className="muted small" style={{ textAlign: 'center' }}>{c}</div>)}
            {r.missing_by_stage.map((s) => [
              <div key={s.deal_stage} className="small strong" style={{ alignSelf: 'center' }}>{s.deal_stage} <span className="muted">({num(s.deals)})</span></div>,
              ...cols.map((c) => (
                <div key={c} title={`${s[c].toFixed(1)}% missing`} style={{ borderRadius: 10, padding: '14px 4px', textAlign: 'center', fontWeight: 600, fontSize: 13,
                                                                            background: rampColor(s[c] / 100), color: s[c] > 55 ? '#fff' : '#0b0b0b' }}>
                  {Math.round(s[c])}%
                </div>
              )),
            ])}
          </div>
        </Card>
        <Card i={2} title="Treatment per column">
          <DataTable rows={r.missing} maxHeight={420} columns={[
            { key: 'column', label: 'Column', render: (m) => <span className="strong">{m.column}</span> },
            { key: 'missing (raw)', label: 'Raw', num: true, render: (m) => num(m['missing (raw)']) },
            { key: 'missing (clean)', label: 'Clean', num: true, render: (m) => num(m['missing (clean)']) },
            { key: 'cause', label: 'Cause' }, { key: 'treatment', label: 'Treatment' },
          ]} />
        </Card>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- normalisation (computed live in the browser)
const quantile = (sorted, q) => {
  const pos = (sorted.length - 1) * q; const lo = Math.floor(pos); const hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
};
function describe(xs) {
  const s = [...xs].sort((a, b) => a - b); const n = s.length;
  const mean = s.reduce((a, b) => a + b, 0) / n;
  const sd = Math.sqrt(s.reduce((a, b) => a + (b - mean) ** 2, 0) / n);
  const skew = sd ? s.reduce((a, b) => a + ((b - mean) / sd) ** 3, 0) / n : 0;
  return { count: n, mean, std: sd, min: s[0], median: quantile(s, 0.5), max: s[n - 1], skewness: skew, q1: quantile(s, 0.25), q3: quantile(s, 0.75) };
}
function scale(xs, method) {
  const d = describe(xs);
  if (method.startsWith('Min-Max')) return xs.map((x) => (d.max - d.min ? (x - d.min) / (d.max - d.min) : 0));
  if (method.startsWith('Z-score')) return xs.map((x) => (d.std ? (x - d.mean) / d.std : 0));
  if (method.startsWith('Robust')) return xs.map((x) => (d.q3 - d.q1 ? (x - d.median) / (d.q3 - d.q1) : 0));
  if (method.startsWith('Log')) return xs.map((x) => Math.log1p(Math.max(x, 0)));
  const k = Math.ceil(Math.log10(Math.max(...xs.map(Math.abs)) + 1));
  return xs.map((x) => x / 10 ** k);
}
function histogram(xs) {
  // Bin count scales with the sample: Sturges for small sets (7 products -> 4 bins), up to 30 for thousands.
  const bins = Math.max(Math.ceil(Math.log2(xs.length) + 1), Math.min(30, Math.ceil(Math.sqrt(xs.length))));
  const min = Math.min(...xs); const max = Math.max(...xs); const w = (max - min) / bins || 1;
  const out = Array.from({ length: bins }, (_, i) => ({ x0: min + i * w, x1: min + (i + 1) * w, n: 0 }));
  xs.forEach((x) => { out[Math.min(bins - 1, Math.floor((x - min) / w))].n += 1; });
  return out.map((b) => ({ ...b, label: fmtNum(b.x0) }));
}
const fmtNum = (v) => (Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(1)}k` : Math.abs(v) >= 10 ? v.toFixed(0) : v.toFixed(2));

function Normalisation({ r }) {
  const cols = Object.keys(r.numeric_columns);
  const methods = Object.keys(r.scalers);
  const [col, setCol] = useState(cols[0]);
  const [method, setMethod] = useState(methods[0]);
  const xs = r.numeric_values[col];
  const after = useMemo(() => scale(xs, method), [xs, method]);
  const [hb, ha] = useMemo(() => [histogram(xs), histogram(after)], [xs, after]);
  const [db, da] = [describe(xs), describe(after)];
  const all = useMemo(() => methods.map((m) => ({ method: m, ...describe(scale(xs, m)) })), [xs, methods]);
  const stats = ['count', 'mean', 'std', 'min', 'median', 'max', 'skewness'];
  const Hist = ({ data, color, t }) => (
    <Card title={t} float={false}>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={data} barCategoryGap={1} margin={{ left: 0, right: 6 }}>
          <CartesianGrid vertical={false} />
          <XAxis dataKey="label" tickLine={false} axisLine={false} interval={Math.max(0, Math.floor(data.length / 6))} />
          <YAxis width={36} tickLine={false} axisLine={false} allowDecimals={false} />
          <Tooltip content={<ChartTip head={(d) => `${fmtNum(d.x0)} – ${fmtNum(d.x1)}`} rows={(d) => [['Values', num(d.n)]]} />} />
          <Bar dataKey="n" fill={color} radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </Card>
  );
  return (
    <div className="stack">
      <Card float={false}>
        <div className="row" style={{ alignItems: 'flex-end', gap: 16 }}>
          <div style={{ width: 300 }}><Field label="Column"><Select value={col} onChange={(v) => setCol(v || cols[0])} options={cols} getLabel={(c) => `${c}: ${r.numeric_columns[c]}`} /></Field></div>
          <Field label="Method"><Seg options={methods} value={method} onChange={setMethod} getLabel={(m) => m.split(' (')[0]} /></Field>
        </div>
        <div className="row" style={{ marginTop: 12 }}><code className="tag" style={{ fontSize: 13, padding: '6px 10px' }}>{r.scalers[method]}</code>
          <span className="muted small">{col === 'close_value' ? 'Won deals only: lost deals are 0 by definition.' : ['revenue', 'employees', 'year_established'].includes(col) ? 'One value per account (85 accounts).' : col === 'sales_price' ? 'One value per product (7 products).' : 'Closed deals.'}</span></div>
      </Card>
      <div className="grid grid-2">
        <Hist data={hb} color={C.blue} t="Before (original units)" />
        <Hist data={ha} color={C.orange} t={`After: ${method}`} />
      </div>
      <div className="grid grid-2">
        <Card i={1} title="Before vs after">
          <DataTable rows={stats.map((s) => ({ stat: s, before: db[s], after: da[s] }))} columns={[
            { key: 'stat', label: 'Statistic', render: (x) => <span className="strong">{x.stat}</span> },
            { key: 'before', label: 'Before', num: true, render: (x) => num(x.before, 4) },
            { key: 'after', label: 'After', num: true, render: (x) => num(x.after, 4) }]} />
        </Card>
        <Card i={2} title="All methods compared" sub="Linear scalers keep the shape. Only the log transform reduces skew.">
          <DataTable rows={all} columns={[
            { key: 'method', label: 'Method', render: (x) => <span className="strong">{x.method.split(' (')[0]}</span> },
            ...['mean', 'std', 'min', 'max', 'skewness'].map((k) => ({ key: k, label: k, num: true, render: (x) => num(x[k], 3) }))]} />
        </Card>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- outliers
function Outliers({ r }) {
  const boxes = Object.entries(r.won_value_by_product).map(([p, xs]) => ({ product: p, ...describe(xs) })).sort((a, b) => a.median - b.median);
  const max = Math.max(...boxes.map((b) => b.max));
  const x = (v) => `${(v / max) * 100}%`;
  return (
    <div className="stack">
      <Card float={false} title="Outlier detection (IQR and z-score)">
        <DataTable rows={r.outliers} columns={[
          { key: 'column', label: 'Column', render: (o) => <span className="strong">{o.column}</span> }, { key: 'description', label: 'Description' },
          { key: 'values', label: 'Values', num: true, render: (o) => num(o.values) },
          { key: 'IQR upper fence', label: 'IQR upper fence', num: true, render: (o) => num(o['IQR upper fence'], 1) },
          { key: 'IQR outliers', label: 'IQR outliers', num: true }, { key: '|z| > 3 outliers', label: '|z| > 3', num: true },
          { key: 'treatment', label: 'Treatment', render: (o) => <span className="ink2">{o.treatment}</span> }]} />
      </Card>
      <Card i={1} title="Won deal value by product" sub="Box = middle 50%, line = median, whiskers = min–max. High values match each product's price.">
        <div className="stack" style={{ gap: 12, paddingTop: 6 }}>
          {boxes.map((b) => (
            <div key={b.product} className="row" style={{ flexWrap: 'nowrap' }} title={`min ${money(b.min)} · Q1 ${money(b.q1)} · median ${money(b.median)} · Q3 ${money(b.q3)} · max ${money(b.max)}`}>
              <div style={{ width: 110 }} className="strong small">{b.product}</div>
              <div style={{ position: 'relative', flex: 1, height: 26 }}>
                <div style={{ position: 'absolute', top: 12, height: 2, left: x(b.min), width: `calc(${x(b.max)} - ${x(b.min)})`, background: C.axis }} />
                <div style={{ position: 'absolute', top: 3, height: 20, left: x(b.q1), width: `max(4px, calc(${x(b.q3)} - ${x(b.q1)}))`, background: '#cde2fb', border: `1.5px solid ${C.blue}`, borderRadius: 6 }} />
                <div style={{ position: 'absolute', top: 1, height: 24, width: 3, left: x(b.median), background: '#184f95', borderRadius: 2 }} />
              </div>
              <div style={{ width: 90 }} className="right small">{money(b.median)}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- encoding + features
function Encoding({ r }) {
  return (
    <div className="stack">
      <Card float={false} title="Categorical encoding">
        <DataTable rows={r.encoding} columns={[{ key: 'column', label: 'Column', render: (e) => <span className="strong">{e.column}</span> },
          { key: 'distinct values', label: 'Distinct', num: true }, { key: 'encoding used', label: 'Encoding' }, { key: 'one-hot columns produced', label: 'Columns produced', num: true }]} />
      </Card>
      <div className="grid grid-2">
        {Object.entries(r.encoding_examples).map(([name, rows], i) => (
          <Card key={name} i={i} title={name}>
            <DataTable rows={rows} columns={Object.keys(rows[0]).map((k) => ({ key: k, label: k, num: typeof rows[0][k] === 'number' }))} />
          </Card>
        ))}
      </div>
      <div className="muted small">One-hot encoding is used for nominal categories. Label encoding is shown for reference only, because it implies an order products don't have. deal_stage is the target, so it is never a model input.</div>
    </div>
  );
}

function Features({ r }) {
  return (
    <div className="stack">
      <Card float={false} title="Derived features">
        <DataTable rows={r.engineered} columns={[{ key: 'feature', label: 'Feature', render: (f) => <span className="strong">{f.feature}</span> },
          { key: 'formula', label: 'Formula' }, { key: 'purpose', label: 'Purpose' }, { key: 'non-missing', label: 'Non-missing', num: true, render: (f) => num(f['non-missing']) },
          { key: 'example', label: 'Example' }]} />
      </Card>
      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))' }}>
        {Object.entries(r.binning).map(([name, rows], i) => {
          const valueKey = Object.keys(rows[0]).find((k) => k !== 'band');
          return (
            <Card key={name} i={i} title={name.split(' (')[0]} sub={name.match(/\((.*)\)/)?.[1]}>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={rows} margin={{ left: 0, right: 6, top: 16 }}>
                  <CartesianGrid vertical={false} />
                  <XAxis dataKey="band" tickLine={false} axisLine={false} interval={0} />
                  <YAxis width={36} tickLine={false} axisLine={false} />
                  <Tooltip content={<ChartTip head={(d) => d.band} rows={(d) => [[valueKey, num(d[valueKey])]]} />} />
                  <Bar dataKey={valueKey} fill={C.blue} radius={[5, 5, 0, 0]} label={{ position: 'top', fill: C.ink2, fontSize: 12 }} />
                </BarChart>
              </ResponsiveContainer>
            </Card>
          );
        })}
      </div>
      <Card float={false} title="Integration (joins)">
        <ul className="ink2" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.9 }}>
          <li><b>sales_pipeline → products</b> on product (many-to-one)</li>
          <li><b>sales_pipeline → sales_teams</b> on sales_agent (many-to-one)</li>
          <li><b>sales_pipeline → accounts</b> on account (many-to-one; left join keeps deals with no account)</li>
          <li>Row count preserved: <b>{num(r.summary.raw_rows)} → {num(r.summary.clean_rows)}</b>. Every join is validated as many-to-one.</li>
        </ul>
      </Card>
    </div>
  );
}
