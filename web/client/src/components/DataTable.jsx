import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight } from 'lucide-react';

import { Empty, Skeleton } from './ui.jsx';

/**
 * columns: [{ key, label, render?(row), num?, sortable? }]
 * Server-side sorting/paging is driven by the parent through sort/onSort and page/onPage.
 */
export default function DataTable({ columns, rows, loading, onRowClick, sort, onSort, page, pageSize, total, onPage,
                                    maxHeight = 560, rowKey = (r, i) => i }) {
  const pages = total ? Math.max(1, Math.ceil(total / pageSize)) : 1;
  return (
    <div>
      <div className="table-wrap" style={{ maxHeight }}>
        <table className="dt">
          <thead>
            <tr>
              {columns.map((c) => {
                const active = sort?.key === c.key;
                return (
                  <th key={c.key} className={`${c.num ? 'num' : ''} ${c.sortable && onSort ? 'sortable' : ''}`}
                      onClick={() => c.sortable && onSort?.({ key: c.key, dir: active && sort.dir === 'desc' ? 'asc' : 'desc' })}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                      {c.label}
                      {active && (sort.dir === 'desc' ? <ArrowDown size={13} /> : <ArrowUp size={13} />)}
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {loading && !rows?.length && Array.from({ length: 8 }, (_, i) => (
              <tr key={i}>{columns.map((c) => <td key={c.key}><Skeleton h={12} /></td>)}</tr>
            ))}
            {rows?.map((r, i) => (
              <tr key={rowKey(r, i)} className={onRowClick ? 'clickable' : ''} onClick={() => onRowClick?.(r)}>
                {columns.map((c) => <td key={c.key} className={c.num ? 'num' : ''}>{c.render ? c.render(r) : (r[c.key] ?? '–')}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && !rows?.length && <Empty>No rows match.</Empty>}
      </div>
      {onPage && total > 0 && (
        <div className="pager">
          <span>{((page - 1) * pageSize + 1).toLocaleString()}–{Math.min(page * pageSize, total).toLocaleString()} of {total.toLocaleString()}</span>
          <div className="row">
            <button className="btn sm" disabled={page <= 1} onClick={() => onPage(page - 1)}><ChevronLeft size={15} /> Prev</button>
            <span className="small">Page {page} / {pages}</span>
            <button className="btn sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next <ChevronRight size={15} /></button>
          </div>
        </div>
      )}
    </div>
  );
}
