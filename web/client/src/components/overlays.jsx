import { AnimatePresence, motion } from 'framer-motion';
import { CheckCircle2, X, XCircle } from 'lucide-react';
import { createContext, useCallback, useContext, useEffect, useState } from 'react';

// ---------------------------------------------------------------- toasts
const ToastCtx = createContext(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }) {
  const [items, setItems] = useState([]);
  const push = useCallback((t) => {
    const id = Math.random().toString(36).slice(2);
    setItems((xs) => [...xs, { id, kind: 'success', ...t }]);
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), t.kind === 'error' ? 7000 : 4000);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" aria-live="polite">
        <AnimatePresence>
          {items.map((t) => (
            <motion.div key={t.id} className={`toast ${t.kind}`} layout
                        initial={{ opacity: 0, x: 40, scale: 0.96 }} animate={{ opacity: 1, x: 0, scale: 1 }}
                        exit={{ opacity: 0, x: 40, scale: 0.96 }} transition={{ type: 'spring', stiffness: 380, damping: 30 }}>
              {t.kind === 'error' ? <XCircle size={20} color="#d03b3b" /> : <CheckCircle2 size={20} color="#0ca30c" />}
              <div style={{ flex: 1 }}>
                <div className="strong">{t.title}</div>
                {t.message && <div className="ink2 small">{t.message}</div>}
                {t.errors?.length > 0 && <ul className="small">{t.errors.map((e) => <li key={e}>{e}</li>)}</ul>}
              </div>
              <button className="btn ghost icon-btn" aria-label="Dismiss"
                      onClick={() => setItems((xs) => xs.filter((x) => x.id !== t.id))}><X size={16} /></button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastCtx.Provider>
  );
}

function useEscape(open, onClose) {
  useEffect(() => {
    if (!open) return undefined;
    const h = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [open, onClose]);
}

// ---------------------------------------------------------------- drawer
export function Drawer({ open, onClose, title, sub, actions, children }) {
  useEscape(open, onClose);
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div className="overlay" onClick={onClose} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
          <motion.aside className="drawer" role="dialog" aria-modal="true"
                        initial={{ x: 80, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 80, opacity: 0 }}
                        transition={{ type: 'spring', stiffness: 320, damping: 32 }}>
            <div className="drawer-head">
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 19, fontWeight: 700, letterSpacing: '-0.01em' }}>{title}</div>
                {sub && <div className="ink2 small" style={{ marginTop: 4 }}>{sub}</div>}
              </div>
              <div className="row" style={{ flexWrap: 'nowrap' }}>
                {actions}
                <button className="btn ghost icon-btn" onClick={onClose} aria-label="Close"><X size={18} /></button>
              </div>
            </div>
            <div className="drawer-body">{children}</div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

// ---------------------------------------------------------------- modal
export function Modal({ open, onClose, title, sub, children }) {
  useEscape(open, onClose);
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div className="overlay" onClick={onClose} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
          <motion.div className="modal" role="dialog" aria-modal="true" style={{ x: '-50%' }}
                      initial={{ opacity: 0, y: 20, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: 12, scale: 0.97 }} transition={{ type: 'spring', stiffness: 360, damping: 30 }}>
            <div className="modal-head">
              <div style={{ fontSize: 18, fontWeight: 700 }}>{title}</div>
              {sub && <div className="ink2 small" style={{ marginTop: 4 }}>{sub}</div>}
            </div>
            <div className="modal-body">{children}</div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
