import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { api } from '../../api/client';
import type { Transaction } from '../../api/types';
import styles from './AddTransactionModal.module.css';

type TxType = 'income' | 'expense';

const CATEGORIES = [
  'Eating Out', 'Groceries', 'Transport', 'Health', 'Personal shopping',
  'Connectivity', 'Entertainment', 'Career & Professional', 'Housing', 'Other',
];

interface Props {
  onClose: () => void;
  onAdd: (tx: Transaction) => void;
}

export function AddTransactionModal({ onClose, onAdd }: Props) {
  const [type, setType]           = useState<TxType>('expense');
  const [amount, setAmount]       = useState('');
  const [merchant, setMerchant]   = useState('');
  const [category, setCategory]   = useState('');
  const [note, setNote]           = useState('');
  const [date, setDate]           = useState(new Date().toISOString().slice(0, 10));
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!amount || isNaN(parseFloat(amount))) return;
    const signed = type === 'income' ? Math.abs(parseFloat(amount)) : -Math.abs(parseFloat(amount));

    setSubmitting(true);
    try {
      const tx = await api.transactions.create({
        booking_date: new Date(date).toISOString(),
        amount: signed,
        currency: 'EUR',
        eur_amount: signed,
        description: note || undefined,
        merchant_name: merchant || undefined,
        category: category || undefined,
      });
      onAdd(tx);
      onClose();
    } catch {
      // API unreachable — insert locally so UI stays responsive
      const localTx: Transaction = {
        id: Date.now(),
        dedup_hash: `manual-${Date.now()}`,
        booking_date: new Date(date).toISOString(),
        amount: signed,
        currency: 'EUR',
        eur_amount: signed,
        description: note || null,
        merchant_name: merchant || null,
        account_id: null,
        is_internal: false,
        category: category || null,
        subcategory: null,
        status: 'verified',
        source: 'manual',
        created_at: new Date().toISOString(),
      };
      onAdd(localTx);
      onClose();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AnimatePresence>
      <motion.div
        className={styles.backdrop}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
      >
        <motion.div
          className={styles.modal}
          initial={{ opacity: 0, y: 40, scale: 0.96 }}
          animate={{ opacity: 1, y: 0,  scale: 1 }}
          exit={{ opacity: 0, y: 40, scale: 0.96 }}
          transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
          onClick={e => e.stopPropagation()}
        >
          <div className={styles.header}>
            <div className={styles.typeTabs}>
              {(['income', 'expense'] as TxType[]).map(t => (
                <button
                  key={t}
                  className={`${styles.typeTab} ${type === t ? styles.typeTabActive : ''} ${styles[t]}`}
                  onClick={() => setType(t)}
                >
                  {t.charAt(0).toUpperCase() + t.slice(1)}
                </button>
              ))}
            </div>
            <button className={styles.closeBtn} onClick={onClose}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6 6 18M6 6l12 12"/></svg>
            </button>
          </div>

          <form className={styles.form} onSubmit={handleSubmit}>
            <div className={styles.amountRow}>
              <span className={styles.currencyLabel}>€</span>
              <input
                className={styles.amountInput}
                type="number"
                step="0.01"
                min="0"
                placeholder="0.00"
                value={amount}
                onChange={e => setAmount(e.target.value)}
                autoFocus
              />
            </div>

            <div className={styles.fields}>
              <label className={styles.field}>
                <span className={styles.fieldLabel}>Merchant / Payee</span>
                <input className={styles.input} value={merchant} onChange={e => setMerchant(e.target.value)} placeholder="e.g. Costa Coffee" />
              </label>

              <label className={styles.field}>
                <span className={styles.fieldLabel}>Date</span>
                <input className={styles.input} type="date" value={date} onChange={e => setDate(e.target.value)} />
              </label>

              <label className={styles.field}>
                <span className={styles.fieldLabel}>Category</span>
                <select className={styles.input} value={category} onChange={e => setCategory(e.target.value)}>
                  <option value="">Select category</option>
                  {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </label>

              <label className={styles.field}>
                <span className={styles.fieldLabel}>Note</span>
                <input className={styles.input} value={note} onChange={e => setNote(e.target.value)} placeholder="Optional note" />
              </label>
            </div>

            <button
              type="submit"
              disabled={submitting}
              className={`${styles.submitBtn} ${type === 'income' ? styles.submitIncome : styles.submitExpense}`}
            >
              {submitting ? 'Saving…' : `Add ${type.charAt(0).toUpperCase() + type.slice(1)}`}
            </button>
          </form>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
