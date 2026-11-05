import { AnimatePresence, motion } from 'framer-motion';
import { GripVertical, Search } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { qs, useApi, useLookups } from '../api.js';
import { useDrawers } from '../components/Drawers.jsx';
import { StageChangeForm } from '../components/forms.jsx';
import { Modal, useToast } from '../components/overlays.jsx';
import { Card, Field, Loading, PageHead, Prob, SearchInput, Select, StagePill } from '../components/ui.jsx';
import { date, money, num } from '../lib/format.js';
import { STAGE_COLORS } from '../lib/palette.js';

const LANES = ['Prospecting', 'Engaging', 'Won', 'Lost'];
const ALLOWED = { Prospecting: ['Engaging', 'Won', 'Lost'], Engaging: ['Won', 'Lost'] };

export default function Pipeline() {
  const { data: lk } = useLookups();
  const [rep, setRep] = useState(null);
  const [q, setQ] = useState('');
  const [drag, setDrag] = useState(null);
  const [over, setOver] = useState(null);
  const [drop, setDrop] = useState(null); // { deal, to }
  const toast = useToast();
  const { openDeal } = useDrawers();

  useEffect(() => { if (!rep && lk?.agents?.length) setRep(lk.agents[0].sales_agent); }, [lk, rep]);
  const { data, isLoading } = useApi(['pipeline', rep], `/pipeline${qs({ rep })}`, { enabled: !!rep });

  const columns = useMemo(() => {
    if (!data) return null;
    const ql = q.toLowerCase();
    const f = (r) => !ql || [r.opportunity_id, r.account, r.product].some((v) => String(v).toLowerCase().includes(ql));
    return Object.fromEntries(LANES.map((l) => [l, data.columns[l].filter(f)]));
  }, [data, q]);

  const onDrop = (lane) => {
    setOver(null);
    if (!drag) return;
    if (drag.deal_stage === lane) return;
    if (!ALLOWED[drag.deal_stage]?.includes(lane)) {
      toast({ kind: 'error', title: 'Not allowed', message: `Deals can't move back from ${drag.deal_stage} to ${lane}.` });
      return;
    }
    setDrop({ deal: drag, to: lane });
  };

  return (
    <>
      <PageHead title="Pipeline board" sub="Drag an open deal to a later stage to update it. Click a card for details.">
        <div style={{ width: 280 }}>
          <Field>
            <Select value={rep} onChange={setRep} options={lk?.agents ?? []} getValue={(a) => a.sales_agent}
                    getLabel={(a) => `${a.sales_agent} · ${a.regional_office}`} />
          </Field>
        </div>
        <SearchInput value={q} onChange={setQ} placeholder="Filter cards…" icon={Search} />
      </PageHead>

      {isLoading || !columns ? <Loading rows={2} h={400} /> : (
        <div className="board">
          {LANES.map((lane, li) => {
            const canDrop = drag && ALLOWED[drag.deal_stage]?.includes(lane);
            const t = data.totals[lane];
            const closedLane = lane === 'Won' || lane === 'Lost';
            return (
              <motion.div key={lane} className={`lane ${over === lane && canDrop ? 'over' : ''} ${drag && !canDrop && drag.deal_stage !== lane ? 'forbidden' : ''}`}
                          initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: li * 0.06 }}
                          onDragOver={(e) => { if (canDrop) { e.preventDefault(); setOver(lane); } }}
                          onDragLeave={() => setOver((o) => (o === lane ? null : o))}
                          onDrop={(e) => { e.preventDefault(); onDrop(lane); }}>
                <div className="lane-head">
                  <div className="lane-title"><span className="dot" style={{ background: STAGE_COLORS[lane] }} />{lane}</div>
                  <div className="lane-count">{num(t.count)} · {money(t.value)}{closedLane ? '' : ' est.'}</div>
                </div>
                <div className="lane-list">
                  <AnimatePresence initial={false}>
                    {columns[lane].map((d) => {
                      const draggable = !closedLane;
                      return (
                        <motion.div key={d.opportunity_id} layout initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }}
                                    exit={{ opacity: 0, scale: 0.96 }}>
                          <div className={`deal-card ${draggable ? '' : 'static'} ${drag?.opportunity_id === d.opportunity_id ? 'dragging' : ''}`}
                               draggable={draggable}
                               onDragStart={(e) => { e.dataTransfer.setData('text/plain', d.opportunity_id); e.dataTransfer.effectAllowed = 'move'; setDrag(d); }}
                               onDragEnd={() => { setDrag(null); setOver(null); }}
                               onClick={() => openDeal(d.opportunity_id)}>
                            <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'nowrap' }}>
                              <div className="t">{d.product}</div>
                              {draggable && <GripVertical size={15} color="#b5b3ab" />}
                            </div>
                            <div className="s">{d.account} · {d.opportunity_id}</div>
                            <div className="b">
                              {closedLane
                                ? <><span className="muted">{date(d.close_date)}</span><b>{d.is_won ? money(d.close_value) : '–'}</b></>
                                : <><div style={{ width: 110 }}><Prob value={d.win_probability} /></div><b>{money(d.est_open_value)}</b></>}
                            </div>
                          </div>
                        </motion.div>
                      );
                    })}
                  </AnimatePresence>
                  {columns[lane].length === 0 && <div className="empty small">No deals</div>}
                  {closedLane && t.count > columns[lane].length && <div className="muted small" style={{ padding: 4 }}>Showing the latest {columns[lane].length}.</div>}
                  {!closedLane && t.count > data.columns[lane].length && <div className="muted small" style={{ padding: 4 }}>Showing {data.columns[lane].length} of {num(t.count)}.</div>}
                </div>
              </motion.div>
            );
          })}
        </div>
      )}

      <Modal open={!!drop} onClose={() => setDrop(null)} title={drop ? `Move ${drop.deal.opportunity_id} to ${drop.to}` : ''}
             sub={drop ? `${drop.deal.product} · ${drop.deal.account}` : ''}>
        {drop && <StageChangeForm key={`${drop.deal.opportunity_id}-${drop.to}`} deal={drop.deal} initialStage={drop.to}
                                  onDone={() => setDrop(null)} onCancel={() => setDrop(null)} />}
      </Modal>
      <Card float={false} className="mt" style={{ padding: '12px 16px' }}>
        <div className="row small ink2">
          <span className="row" style={{ gap: 6 }}><StagePill stage="Prospecting" /> → <StagePill stage="Engaging" /> → <StagePill stage="Won" /> or <StagePill stage="Lost" /></span>
          <span>Closed deals can’t be reopened. Every move is validated: closed deals need a close date and an account, and Won deals need a value.</span>
        </div>
      </Card>
    </>
  );
}
