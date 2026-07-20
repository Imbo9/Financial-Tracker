import { useState } from 'react';
import { useParams, useSearchParams, useNavigate, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { statsQueries, transactionQueries } from '../../api/queries';
import styles from './CategoryDetailPage.module.css';

const ALL = 'All';
const TREND_MONTHS = 12;
const DAYS_BACK = 30;
const TX_LIMIT = 20;

function formatMonth(iso: string): string {
  const [y, m] = iso.split('-');
  return new Date(parseInt(y), parseInt(m) - 1).toLocaleDateString('it-IT', { month: 'short' });
}

function formatDay(iso: string): string {
  return new Date(iso).toLocaleDateString('it-IT', { day: '2-digit', month: 'short' });
}

interface TrendTooltipProps {
  active?: boolean;
  payload?: Array<{ value?: number | string }>;
  label?: string;
}

const TrendTooltip = ({ active, payload, label }: TrendTooltipProps) => {
  if (!active || !payload?.length) return null;
  return (
    <div className={styles.tooltip}>
      <div>{formatMonth(label ?? '')}</div>
      <div className={styles.tooltipValue}>
        €{Number(payload[0]?.value).toLocaleString('it-IT', { minimumFractionDigits: 2 })}
      </div>
    </div>
  );
};

export function CategoryDetailPage() {
  const { category = '' } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const direction = searchParams.get('direction') === 'income' ? 'income' : 'expense';

  const [selectedSub, setSelectedSub] = useState<string>(ALL);
  const subFilter = selectedSub === ALL ? undefined : selectedSub;

  const subcategories = useQuery({
    ...statsQueries.subcategories(category, DAYS_BACK, direction),
  });
  const trend = useQuery({
    ...statsQueries.categoryTrend(category, TREND_MONTHS, direction, subFilter),
  });
  const transactions = useQuery({
    ...transactionQueries.list({
      category,
      subcategory: subFilter,
      direction,
      days_back: DAYS_BACK,
      page_size: TX_LIMIT,
    }),
  });

  const subData = subcategories.data ?? [];
  const trendData = trend.data ?? [];
  const txItems = transactions.data?.items ?? [];
  const periodTotal = subData.reduce((s, r) => s + r.total, 0);

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <button className={styles.back} onClick={() => navigate(-1)} aria-label="Indietro">
          ←
        </button>
        <div>
          <h1 className={styles.title}>{category}</h1>
          <span className={styles.subtitle}>
            € {periodTotal.toLocaleString('it-IT', { minimumFractionDigits: 2 })} · ultimi 30 giorni
          </span>
        </div>
      </header>

      <main className={styles.main}>
        {subData.length > 0 && (
          <section className={styles.section}>
            <h2 className={styles.sectionTitle}>Subcategories</h2>
            {subcategories.isError && (
              <div className={styles.stateMsg}>Impossibile caricare le sottocategorie — riprova.</div>
            )}
            <div className={styles.chips}>
              <button
                className={`${styles.chip} ${selectedSub === ALL ? styles.chipActive : ''}`}
                onClick={() => setSelectedSub(ALL)}
              >
                {ALL}
              </button>
              {subData.map(s => (
                <button
                  key={s.subcategory}
                  className={`${styles.chip} ${selectedSub === s.subcategory ? styles.chipActive : ''}`}
                  onClick={() => setSelectedSub(s.subcategory)}
                >
                  {s.subcategory} <span className={styles.chipPct}>{s.percentage.toFixed(0)}%</span>
                </button>
              ))}
            </div>
          </section>
        )}

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>12-Month Trend</h2>
          {trend.isError && (
            <div className={styles.stateMsg}>Impossibile caricare l'andamento — riprova.</div>
          )}
          <ResponsiveContainer width="100%" height={200}>
            {/* isAnimationActive: rAF is frozen in background tabs, which would leave this blank */}
            <LineChart data={trendData}>
              <CartesianGrid vertical={false} stroke="var(--border)" />
              <XAxis
                dataKey="month"
                tickFormatter={formatMonth}
                tick={{ fontFamily: 'var(--font-mono)', fontSize: 10, fill: 'var(--text-muted)' }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fontFamily: 'var(--font-mono)', fontSize: 10, fill: 'var(--text-muted)' }}
                tickFormatter={v => `€${Math.round(v)}`}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip content={<TrendTooltip />} />
              <Line
                type="monotone"
                dataKey="total"
                stroke="var(--accent)"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Transactions</h2>
          {transactions.isError && (
            <div className={styles.stateMsg}>Impossibile caricare le transazioni — riprova.</div>
          )}
          {!transactions.isError && txItems.length === 0 && (
            <div className={styles.stateMsg}>Nessuna transazione in questo periodo.</div>
          )}
          {txItems.map((tx, i) => (
            <motion.div
              key={tx.id}
              className={styles.txRow}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.03, duration: 0.25 }}
            >
              <div className={styles.txInfo}>
                <span className={styles.txMerchant}>
                  {tx.merchant_name ?? tx.description ?? '—'}
                </span>
                <span className={styles.txMeta}>{formatDay(tx.booking_date)}</span>
              </div>
              <span className={styles.txAmount}>
                €{Math.abs(tx.eur_amount).toFixed(2)}
              </span>
            </motion.div>
          ))}
          <Link
            className={styles.seeAll}
            to={`/transactions?category=${encodeURIComponent(category)}`}
          >
            See all
          </Link>
        </section>
      </main>
    </div>
  );
}
