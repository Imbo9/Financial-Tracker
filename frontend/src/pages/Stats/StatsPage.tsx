import { useState } from 'react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts';
import { motion } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { statsQueries } from '../../api/queries';
import { AnimatedNumber } from '../../components/AnimatedNumber';
import styles from './StatsPage.module.css';

const COLORS = [
  'var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)',
  'var(--chart-5)', 'var(--chart-6)', 'var(--chart-7)', 'var(--chart-8)',
];

type Tab = 'expenses' | 'income';

function formatMonth(iso: string): string {
  const [y, m] = iso.split('-');
  return new Date(parseInt(y), parseInt(m) - 1).toLocaleDateString('it-IT', { month: 'short' });
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{ name?: string; value?: number | string }>;
}

const CustomTooltip = ({ active, payload }: CustomTooltipProps) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: 'var(--bg-elevated)',
      border: '1px solid var(--border-strong)',
      borderRadius: 8,
      padding: '8px 12px',
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-primary)',
    }}>
      <div>{payload[0]?.name}</div>
      <div style={{ color: 'var(--accent)', fontWeight: 600 }}>€{Number(payload[0]?.value).toFixed(2)}</div>
    </div>
  );
};

export function StatsPage() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>('expenses');
  const [activeIdx, setActiveIdx] = useState<number | null>(null);

  const categories = useQuery({
    ...statsQueries.categories(30, tab === 'income' ? 'income' : 'expense'),
  });
  const monthly = useQuery({ ...statsQueries.monthly(12) });
  const categoryData = categories.data ?? [];
  const monthlyData = monthly.data ?? [];
  const isError = categories.isError || monthly.isError;

  const total = categoryData.reduce((s, c) => s + c.total, 0);

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>Statistics</h1>
        <div className={styles.tabs}>
          {(['expenses', 'income'] as Tab[]).map(t => (
            <button
              key={t}
              className={`${styles.tab} ${tab === t ? styles.tabActive : ''} ${t === 'income' ? styles.tabIncome : styles.tabExpense}`}
              onClick={() => setTab(t)}
            >
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>
      </header>

      <main className={styles.main}>
        {isError && <div className={styles.stateMsg}>Impossibile caricare le statistiche — riprova.</div>}

        <motion.section
          className={styles.pieSection}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        >
          <div className={styles.pieWrap}>
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie
                  data={categoryData}
                  dataKey="total"
                  nameKey="category"
                  cx="50%"
                  cy="50%"
                  innerRadius={70}
                  outerRadius={110}
                  paddingAngle={3}
                  // rAF-driven sector tween never fires in background tabs (Chrome
                  // freezes rAF for hidden documents), leaving the donut empty.
                  isAnimationActive={false}
                  onMouseEnter={(_, idx) => setActiveIdx(idx)}
                  onMouseLeave={() => setActiveIdx(null)}
                >
                  {categoryData.map((_, i) => (
                    <Cell
                      key={i}
                      fill={COLORS[i % COLORS.length]}
                      opacity={activeIdx === null || activeIdx === i ? 1 : 0.35}
                      stroke="none"
                    />
                  ))}
                </Pie>
                <Tooltip content={<CustomTooltip />} />
              </PieChart>
            </ResponsiveContainer>

            <div className={styles.pieCenter}>
              <span className={styles.pieCenterLabel}>Total</span>
              <AnimatedNumber value={total} prefix="€ " decimals={0} className={styles.pieCenterValue} />
            </div>
          </div>

          <div className={styles.legend}>
            {categoryData.map((cat, i) => (
              <motion.button
                key={cat.category}
                type="button"
                className={styles.legendItem}
                initial={{ opacity: 0, x: -12 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05, duration: 0.3 }}
                onMouseEnter={() => setActiveIdx(i)}
                onMouseLeave={() => setActiveIdx(null)}
                onClick={() =>
                  navigate(
                    `/stats/category/${encodeURIComponent(cat.category)}?direction=${
                      tab === 'income' ? 'income' : 'expense'
                    }`,
                  )
                }
                style={{ opacity: activeIdx === null || activeIdx === i ? 1 : 0.4 }}
              >
                <span className={styles.legendDot} style={{ background: COLORS[i % COLORS.length] }} />
                <span className={styles.legendName}>{cat.category}</span>
                <span className={styles.legendPct}>{cat.percentage.toFixed(1)}%</span>
                <span className={styles.legendAmount}>€{cat.total.toFixed(2)}</span>
              </motion.button>
            ))}
          </div>
        </motion.section>

        <motion.section
          className={styles.barSection}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        >
          <h2 className={styles.sectionTitle}>Monthly Overview</h2>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={[...monthlyData].reverse()} barGap={4} barCategoryGap="35%">
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
                axisLine={false}
                tickLine={false}
                tickFormatter={v => `€${(v/1000).toFixed(0)}k`}
              />
              <Tooltip content={<CustomTooltip />} />
              {/* isAnimationActive: same background-tab rAF freeze as the Pie above */}
              <Bar dataKey="income"   name="Income"   fill="var(--income)"  radius={[4,4,0,0]} isAnimationActive={false} />
              <Bar dataKey="expenses" name="Expenses" fill="var(--expense)" radius={[4,4,0,0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </motion.section>

        <motion.section
          className={styles.monthlyList}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        >
          <h2 className={styles.sectionTitle}>By Month</h2>
          {[...monthlyData].filter(m => m.income > 0 || m.expenses > 0).map((m) => (
            <div key={m.month} className={styles.monthRow}>
              <span className={styles.monthName}>{formatMonth(m.month)} {m.month.slice(0, 4)}</span>
              <span className={styles.monthIncome}>+€{m.income.toLocaleString('it-IT', { maximumFractionDigits: 0 })}</span>
              <span className={styles.monthExpense}>-€{m.expenses.toLocaleString('it-IT', { maximumFractionDigits: 0 })}</span>
              <span className={`${styles.monthNet} ${m.net >= 0 ? styles.netPos : styles.netNeg}`}>
                {m.net >= 0 ? '+' : ''}€{Math.abs(m.net).toLocaleString('it-IT', { maximumFractionDigits: 0 })}
              </span>
            </div>
          ))}
        </motion.section>
      </main>
    </div>
  );
}
