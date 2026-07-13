import { motion } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { AnimatedNumber } from '../../components/AnimatedNumber';
import { accountQueries, statsQueries } from '../../api/queries';
import type { AccountsResponse } from '../../api/types';
import styles from './AccountsPage.module.css';

const DEFAULT_DATA: AccountsResponse = { assets: 0, liabilities: 0, accounts: [] };

function accountIcon(balance: number) {
  return balance >= 0 ? '◇' : '◈';
}

function formatMonth(iso: string): string {
  const [y, m] = iso.split('-');
  return new Date(parseInt(y), parseInt(m) - 1).toLocaleDateString('it-IT', { month: 'short' });
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{ name?: string; value?: number | string }>;
  label?: string;
}

const CustomTooltip = ({ active, payload, label }: CustomTooltipProps) => {
  if (!active || !payload?.length) return null;
  return (
    <div
      style={{
        background: 'var(--bg-elevated)',
        border: '1px solid var(--border-strong)',
        borderRadius: 8,
        padding: '8px 12px',
        fontFamily: 'var(--font-mono)',
        fontSize: 12,
        color: 'var(--text-primary)',
      }}
    >
      <div>{formatMonth(label ?? '')}</div>
      <div style={{ color: 'var(--accent)', fontWeight: 600 }}>€{Number(payload[0]?.value).toLocaleString('it-IT')}</div>
    </div>
  );
};

export function AccountsPage() {
  const { data, isError } = useQuery({ ...accountQueries.list() });
  const accounts = data ?? DEFAULT_DATA;

  const history = useQuery({ ...statsQueries.balanceHistory(12) });
  const historyData = history.data ?? [];

  const total = accounts.assets - accounts.liabilities;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>Accounts</h1>
      </header>

      <main className={styles.main}>
        {isError && <div className={styles.stateMsg}>Impossibile caricare i conti — riprova.</div>}

        <motion.section
          className={styles.hero}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        >
          <span className={styles.heroLabel}>Net Worth</span>
          <AnimatedNumber value={total} prefix="€ " decimals={2} className={styles.heroValue} />
          <div className={styles.heroSplit}>
            <div className={styles.heroItem}>
              <span className={styles.heroItemLabel}>Assets</span>
              <AnimatedNumber value={accounts.assets} prefix="€ " decimals={0} className={styles.income} />
            </div>
            <div className={styles.heroItemDivider} />
            <div className={styles.heroItem}>
              <span className={styles.heroItemLabel}>Liabilities</span>
              <AnimatedNumber value={accounts.liabilities} prefix="€ " decimals={0} className={styles.expense} />
            </div>
          </div>
        </motion.section>

        <section className={styles.listSection}>
          <h2 className={styles.sectionTitle}>Balance</h2>
          <ResponsiveContainer width="100%" height={200}>
            {/* isAnimationActive: background-tab rAF freeze, same as StatsPage charts */}
            <LineChart data={historyData}>
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
                tickFormatter={v => `€${Math.round(v / 1000)}k`}
                axisLine={false}
                tickLine={false}
                domain={['auto', 'auto']}
              />
              <Tooltip content={<CustomTooltip />} />
              <Line
                type="monotone"
                dataKey="balance"
                stroke="var(--accent)"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </section>

        <section className={styles.listSection}>
          <h2 className={styles.sectionTitle}>All Accounts</h2>
          {accounts.accounts.map((acc, i) => (
            <motion.div
              key={acc.account_id}
              className={styles.accountRow}
              initial={{ opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.06, duration: 0.3 }}
            >
              <div className={styles.accountIcon}>{accountIcon(acc.balance)}</div>
              <div className={styles.accountInfo}>
                <span className={styles.accountName}>{acc.display_name ?? acc.account_id}</span>
              </div>
              <AnimatedNumber
                value={acc.balance}
                prefix="€ "
                decimals={2}
                className={`${styles.accountBalance} ${acc.balance < 0 ? styles.expense : ''}`}
              />
            </motion.div>
          ))}
        </section>

        <div className={styles.syncNote}>
          <span className={styles.syncDot} />
          <span>Balances synced from Enable Banking · 4×/day</span>
        </div>
      </main>
    </div>
  );
}
