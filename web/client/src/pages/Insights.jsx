import { Gauge, RefreshCw, Scale, Sparkles, Target } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from 'recharts';

import { api, useApi } from '../api.js';
import DataTable from '../components/DataTable.jsx';
import { useWrite } from '../components/forms.jsx';
import { Alert, Card, ChartTip, KpiCard, Loading, PageHead } from '../components/ui.jsx';
import { date, num, pct } from '../lib/format.js';
import { BLUE_RAMP, C } from '../lib/palette.js';

const ROC_COLORS = { 'Logistic Regression': C.blue, 'Decision Tree': C.orange, 'Random Forest': C.aqua, 'Gradient Boosting': C.yellow };

export default function Insights() {
  const { data: m } = useApi('model', '/model');
  const rescore = useWrite(() => api('/jobs/predictions', { method: 'POST' }), { success: { title: 'Model retrained and deals re-scored' } });

  if (!m) return <><PageHead title="Win prediction" /><Loading rows={3} h={360} /></>;
  if (!m.available) return <><PageHead title="Win prediction" /><Alert kind="error" title="The model could not be trained">{m.error}</Alert></>;

  const test = m.comparison.filter((r) => r.split === 'test');
  const base = test.find((r) => r.model.startsWith('Prior'));
  const tm = m.test_metrics;
  const cm = m.confusion;
  const cmMax = Math.max(...cm.flat());
  const roc = Object.entries(m.roc).filter(([k]) => !k.startsWith('Prior'));

  return (
    <>
      <PageHead title="Win prediction" sub={`Will an open opportunity end as Won? Model trained on closed deals · last scored ${date(m.scored_at)}`}>
        <button className="btn" onClick={() => rescore.mutate()} disabled={rescore.isPending}>
          <RefreshCw size={16} className={rescore.isPending ? 'spin' : ''} /> {rescore.isPending ? 'Retraining…' : 'Retrain & re-score'}
        </button>
      </PageHead>

      <div className="stack" style={{ marginBottom: 16 }}>
        <Alert kind="info">This dataset has no separate lead records, so “convert” means an open <b>opportunity</b> (Prospecting / Engaging) ending as <b>Won</b>.</Alert>
        {m.warnings.map((w) => <Alert key={w} kind="warn">{w}</Alert>)}
      </div>

      <div className="grid grid-kpi">
        <KpiCard i={0} label="Selected model" value={m.best_model} icon={Sparkles} sub="chosen on validation ROC-AUC" />
        <KpiCard i={1} label="Test ROC-AUC" value={tm.roc_auc} format={(v) => v.toFixed(3)} icon={Gauge} sub={`95% CI ${m.auc_ci[0].toFixed(2)}–${m.auc_ci[1].toFixed(2)} · 0.5 = random`} />
        <KpiCard i={2} label="Test accuracy" value={tm.accuracy} format={(v) => pct(v)} icon={Target} sub={`always-“Won” baseline ${pct(base?.accuracy)}`} />
        <KpiCard i={3} label="Decision threshold" value={m.threshold} format={(v) => v.toFixed(3)} icon={Scale} sub="tuned for balanced accuracy" />
        <KpiCard i={4} label="Open deals predicted Yes" value={m.n_predicted_yes} format={(v) => num(Math.round(v))} sub={`of ${num(m.n_scored)} scored`} />
      </div>

      <div className="grid grid-2">
        <Card i={1} title="ROC curves (test split)" sub="A curve on the diagonal means no ability to rank wins above losses">
          <ResponsiveContainer width="100%" height={300}>
            <LineChart margin={{ left: 0, right: 10, top: 6, bottom: 10 }}>
              <CartesianGrid />
              <XAxis type="number" dataKey="fpr" domain={[0, 1]} tickLine={false} axisLine={false} tickFormatter={(v) => v.toFixed(1)}
                     label={{ value: 'False positive rate', position: 'insideBottom', offset: -6, fill: C.muted, fontSize: 12 }} />
              <YAxis type="number" domain={[0, 1]} tickLine={false} axisLine={false} width={36} tickFormatter={(v) => v.toFixed(1)} />
              <Line data={[{ fpr: 0, tpr: 0 }, { fpr: 1, tpr: 1 }]} dataKey="tpr" stroke={C.axis} strokeWidth={1.5} dot={false} name="Random" isAnimationActive={false} />
              {roc.map(([name, pts]) => <Line key={name} data={pts} dataKey="tpr" stroke={ROC_COLORS[name]} strokeWidth={2} dot={false} name={name} />)}
              <Legend verticalAlign="top" height={30} iconType="plainline" wrapperStyle={{ fontSize: 12 }} />
              <Tooltip formatter={(v) => v.toFixed(3)} labelFormatter={(v) => `FPR ${Number(v).toFixed(2)}`} />
            </LineChart>
          </ResponsiveContainer>
        </Card>
        <Card i={2} title="Calibration (test split)" sub="Do deals scored 0.65 actually win about 65% of the time?">
          <ResponsiveContainer width="100%" height={300}>
            <ScatterChart margin={{ left: 0, right: 10, top: 6, bottom: 10 }}>
              <CartesianGrid />
              <XAxis type="number" dataKey="mean_predicted" domain={[0.3, 0.9]} tickLine={false} axisLine={false}
                     label={{ value: 'Mean predicted probability', position: 'insideBottom', offset: -6, fill: C.muted, fontSize: 12 }} />
              <YAxis type="number" dataKey="observed_win_rate" domain={[0.3, 0.9]} tickLine={false} axisLine={false} width={36} />
              <Scatter data={[{ mean_predicted: 0.3, observed_win_rate: 0.3 }, { mean_predicted: 0.9, observed_win_rate: 0.9 }]} line={{ stroke: C.axis, strokeWidth: 1.5 }} shape={() => null} isAnimationActive={false} />
              <Scatter data={m.calibration} fill={C.blue} line={{ stroke: C.blue, strokeWidth: 2 }} stroke="#fff" strokeWidth={2} />
              <Tooltip content={<ChartTip head={() => 'Calibration bin'} rows={(d) => [['Predicted', d.mean_predicted.toFixed(2)], ['Observed', d.observed_win_rate.toFixed(2)]]} />} />
            </ScatterChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <div className="grid grid-2-3 mt">
        <Card i={3} title="Confusion matrix" sub={`${m.best_model}, test split`}>
          <div style={{ display: 'grid', gridTemplateColumns: '90px 1fr 1fr', gap: 6, alignItems: 'stretch' }}>
            <div />
            <div className="muted small right" style={{ textAlign: 'center' }}>Predicted Lost</div>
            <div className="muted small" style={{ textAlign: 'center' }}>Predicted Won</div>
            {[['Actual Lost', ['True negative', 'False positive']], ['Actual Won', ['False negative', 'True positive']]].map(([rowLabel, names], i) => [
              <div key={rowLabel} className="muted small" style={{ alignSelf: 'center' }}>{rowLabel}</div>,
              ...cm[i].map((v, j) => {
                const t = v / cmMax;
                return (
                  <div key={`${i}${j}`} style={{ borderRadius: 14, padding: '22px 10px', textAlign: 'center',
                                                 background: BLUE_RAMP[Math.round(1 + t * 5)], color: t > 0.5 ? '#fff' : '#0b0b0b' }}>
                    <div style={{ fontSize: 24, fontWeight: 700 }}>{num(v)}</div>
                    <div className="small" style={{ opacity: 0.85 }}>{names[j]}</div>
                  </div>
                );
              }),
            ])}
          </div>
          <div className="muted small" style={{ marginTop: 10 }}>Precision {pct(tm.precision)} · Recall {pct(tm.recall)} · F1 {tm.f1.toFixed(3)} · Brier {tm.brier.toFixed(3)}</div>
        </Card>
        <Card i={4} title="Permutation importance" sub="Drop in test ROC-AUC when a feature is shuffled. Near zero means no signal.">
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={m.importance} layout="vertical" margin={{ left: 8, right: 20 }} barCategoryGap={5}>
              <CartesianGrid horizontal={false} />
              <XAxis type="number" tickLine={false} axisLine={false} tickFormatter={(v) => v.toFixed(3)} />
              <YAxis type="category" dataKey="feature" width={120} tickLine={false} axisLine={false} />
              <Tooltip content={<ChartTip head={(d) => d.feature} rows={(d) => [['AUC drop', d.auc_drop_mean.toFixed(4)], ['± std', d.auc_drop_std.toFixed(4)]]} />} />
              <Bar dataKey="auc_drop_mean" fill={C.blue} radius={[0, 5, 5, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <Card i={5} className="mt" title="Model comparison" sub={`Chronological split: train ${num(m.split_info.train.rows)} (${m.split_info.train.from} → ${m.split_info.train.to}), validation ${num(m.split_info.validation.rows)}, test ${num(m.split_info.test.rows)} (${m.split_info.test.from} → ${m.split_info.test.to})`}>
        <DataTable rows={test} rowKey={(r) => r.model} columns={[
          { key: 'model', label: 'Model (test split)', render: (r) => <span className={r.model === m.best_model ? 'strong' : ''}>{r.model}{r.model === m.best_model ? '  ★' : ''}</span> },
          ...['roc_auc', 'accuracy', 'balanced_accuracy', 'precision', 'recall', 'f1', 'brier'].map((k) => ({ key: k, label: k.replace('_', ' '), num: true, render: (r) => r[k].toFixed(3) })),
        ]} />
      </Card>

      <div className="grid grid-2 mt">
        <Card i={6} title="Features used" sub="Only information known while a deal is still open">
          <div className="row" style={{ gap: 6 }}>{m.features.map((f) => <span key={f} className="tag">{f}</span>)}</div>
        </Card>
        <Card i={7} title="Excluded to prevent leakage">
          {m.excluded.map((e) => <div key={e.column} className="feed-item"><span className="tag">{e.column}</span><span className="ink2 small">{e.reason}</span></div>)}
        </Card>
      </div>
    </>
  );
}
