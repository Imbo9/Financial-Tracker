import { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { Transaction } from '../../api/types';
import { transactionQueries, taxonomyQueries } from '../../api/queries';
import { AnimatedNumber } from '../../components/AnimatedNumber';
import { AddTransactionModal } from './AddTransactionModal';
import styles from './TransactionsPage.module.css';

type ViewMode = 'daily' | 'monthly';

function groupByDate(txs: Transaction[]): Record<string, Transaction[]> {
  return txs.reduce<Record<string, Transaction[]>>((acc, tx) => {
    const day = tx.booking_date.slice(0, 10);
    (acc[day] ??= []).push(tx);
    return acc;
  }, {});
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString('it-IT', { weekday: 'short', day: 'numeric', month: 'long' });
}

function formatMonth(iso: string): string {
  const d = new Date(iso + '-01');
  return d.toLocaleDateString('it-IT', { month: 'long', year: 'numeric' });
}

function groupByMonth(txs: Transaction[]): Record<string, Transaction[]> {
  return txs.reduce<Record<string, Transaction[]>>((acc, tx) => {
    const month = tx.booking_date.slice(0, 7);
    (acc[month] ??= []).push(tx);
    return acc;
  }, {});
}

function categoryInitial(cat: string | null): string {
  if (!cat) return '?';
  return cat[0].toUpperCase();
}

export function TransactionsPage() {
  const [view, setView] = useState<ViewMode>('daily');
  const [search, setSearch] = useState('');
  const [showAdd, setShowAdd] = useState(false);

  const queryClient = useQueryClient();
  const { data, isPending, isError } = useQuery({
    ...transactionQueries.list({ days_back: 90, page_size: 500 }),
  });
  const transactions = useMemo(() => data?.items ?? [], [data]);

  const { data: taxonomy } = useQuery({ ...taxonomyQueries.categories() });
  const categoryOrder = useMemo(
    () => [...Object.keys(taxonomy?.expense ?? {}), ...Object.keys(taxonomy?.income ?? {})],
    [taxonomy],
  );
  const colorOf = (cat: string | null): string => {
    const i = cat ? categoryOrder.indexOf(cat) : -1;
    return i === -1 ? 'var(--text-muted)' : `var(--chart-${(i % 8) + 1})`;
  };

  const filtered = useMemo(() =>
    search
      ? transactions.filter(t =>
          (t.merchant_name ?? '').toLowerCase().includes(search.toLowerCase()) ||
          (t.description ?? '').toLowerCase().includes(search.toLowerCase()) ||
          (t.category ?? '').toLowerCase().includes(search.toLowerCase())
        )
      : transactions,
    [transactions, search]
  );

  const totalIncome   = filtered.filter(t => t.amount > 0).reduce((s, t) => s + t.eur_amount, 0);
  const totalExpenses = filtered.filter(t => t.amount < 0).reduce((s, t) => s + Math.abs(t.eur_amount), 0);

  const dailyGroups   = groupByDate(filtered);
  const monthlyGroups = groupByMonth(filtered);

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.headerTop}>
          <h1 className={styles.title}>Transactions</h1>
          <button className={styles.addBtn} onClick={() => setShowAdd(true)} title="Add transaction">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"><path d="M12 5v14M5 12h14"/></svg>
          </button>
        </div>

        <div className={styles.summary}>
          <div className={styles.summaryItem}>
            <span className={styles.summaryLabel}>Income</span>
            <AnimatedNumber value={totalIncome} prefix="€ " className={`${styles.summaryValue} ${styles.income}`} />
          </div>
          <div className={styles.summaryDivider} />
          <div className={styles.summaryItem}>
            <span className={styles.summaryLabel}>Expenses</span>
            <AnimatedNumber value={totalExpenses} prefix="€ " className={`${styles.summaryValue} ${styles.expense}`} />
          </div>
          <div className={styles.summaryDivider} />
          <div className={styles.summaryItem}>
            <span className={styles.summaryLabel}>Net</span>
            <AnimatedNumber
              value={Math.abs(totalIncome - totalExpenses)}
              prefix={totalIncome - totalExpenses >= 0 ? '+€ ' : '-€ '}
              className={`${styles.summaryValue} ${totalIncome >= totalExpenses ? styles.income : styles.expense}`}
            />
          </div>
        </div>

        <div className={styles.controls}>
          <div className={styles.toggle}>
            {(['daily', 'monthly'] as ViewMode[]).map(v => (
              <button
                key={v}
                className={`${styles.toggleBtn} ${view === v ? styles.toggleActive : ''}`}
                onClick={() => setView(v)}
              >
                {v.charAt(0).toUpperCase() + v.slice(1)}
              </button>
            ))}
          </div>
          <div className={styles.searchWrap}>
            <svg className={styles.searchIcon} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
            <input
              className={styles.search}
              placeholder="Search..."
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
        </div>
      </header>

      <main className={styles.main}>
        {isPending && <div className={styles.loadingMsg}>Loading…</div>}
        {isError && <div className={styles.loadingMsg}>Impossibile caricare le transazioni — riprova.</div>}

        {view === 'daily' && (
          <AnimatePresence>
            {Object.entries(dailyGroups)
              .sort(([a], [b]) => b.localeCompare(a))
              .map(([date, txs], gi) => (
                <motion.section
                  key={date}
                  className={styles.group}
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: gi * 0.04, duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
                >
                  <div className={styles.groupHeader}>
                    <span className={styles.groupDate}>{formatDate(date)}</span>
                    <span className={styles.groupTotal}>
                      {txs.reduce((s, t) => s + t.eur_amount, 0) >= 0 ? '+' : ''}
                      €{Math.abs(txs.reduce((s, t) => s + t.eur_amount, 0)).toFixed(2)}
                    </span>
                  </div>
                  {txs.map((tx, i) => <TxRow key={tx.id} tx={tx} index={i} color={colorOf(tx.category)} />)}
                </motion.section>
              ))}
          </AnimatePresence>
        )}

        {view === 'monthly' && (
          <AnimatePresence>
            {Object.entries(monthlyGroups)
              .sort(([a], [b]) => b.localeCompare(a))
              .map(([month, txs], gi) => {
                const income   = txs.filter(t => t.amount > 0).reduce((s, t) => s + t.eur_amount, 0);
                const expenses = txs.filter(t => t.amount < 0).reduce((s, t) => s + Math.abs(t.eur_amount), 0);
                return (
                  <motion.section
                    key={month}
                    className={styles.group}
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: gi * 0.06, duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
                  >
                    <div className={styles.groupHeader}>
                      <span className={styles.groupDate}>{formatMonth(month)}</span>
                      <div className={styles.monthStats}>
                        <span className={styles.income}>+€{income.toFixed(2)}</span>
                        <span className={styles.expense}>-€{expenses.toFixed(2)}</span>
                      </div>
                    </div>
                    {txs.map((tx, i) => <TxRow key={tx.id} tx={tx} index={i} color={colorOf(tx.category)} />)}
                  </motion.section>
                );
              })}
          </AnimatePresence>
        )}
      </main>

      {showAdd && <AddTransactionModal onClose={() => setShowAdd(false)} onAdd={() => queryClient.invalidateQueries({ queryKey: ['transactions'] })} />}
    </div>
  );
}

function TxRow({ tx, index, color }: { tx: Transaction; index: number; color: string }) {
  const isIncome = tx.amount > 0;
  const initial = categoryInitial(tx.category);

  return (
    <motion.div
      className={styles.txRow}
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.03, duration: 0.25 }}
      whileHover={{ backgroundColor: 'var(--bg-hover)' }}
    >
      <div className={styles.txIcon} style={{ '--cat-color': color } as React.CSSProperties}>
        {initial}
      </div>
      <div className={styles.txInfo}>
        <span className={styles.txMerchant}>{tx.merchant_name ?? tx.description ?? '—'}</span>
        <span className={styles.txMeta}>
          {tx.category ?? 'Uncategorized'}
          {tx.status === 'pending' && <span className={styles.pendingBadge}>pending</span>}
        </span>
      </div>
      <div className={styles.txAmount}>
        <span className={`${styles.txAmountValue} ${isIncome ? styles.income : styles.expense}`}>
          {isIncome ? '+' : ''}€{Math.abs(tx.eur_amount).toFixed(2)}
        </span>
        {tx.currency !== 'EUR' && (
          <span className={styles.txCurrency}>{tx.currency}</span>
        )}
      </div>
    </motion.div>
  );
}
