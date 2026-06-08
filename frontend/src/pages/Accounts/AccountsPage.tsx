import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { AnimatedNumber } from '../../components/AnimatedNumber';
import { api } from '../../api/client';
import type { AccountsResponse } from '../../api/types';
import styles from './AccountsPage.module.css';

const DEFAULT_DATA: AccountsResponse = { assets: 0, liabilities: 0, accounts: [] };

function accountIcon(balance: number) {
  return balance >= 0 ? '◇' : '◈';
}

export function AccountsPage() {
  const [data, setData] = useState<AccountsResponse>(DEFAULT_DATA);

  useEffect(() => {
    api.accounts.list().then(setData).catch(() => {});
  }, []);

  const total = data.assets - data.liabilities;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>Accounts</h1>
      </header>

      <main className={styles.main}>
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
              <AnimatedNumber value={data.assets} prefix="€ " decimals={0} className={styles.income} />
            </div>
            <div className={styles.heroItemDivider} />
            <div className={styles.heroItem}>
              <span className={styles.heroItemLabel}>Liabilities</span>
              <AnimatedNumber value={data.liabilities} prefix="€ " decimals={0} className={styles.expense} />
            </div>
          </div>
        </motion.section>

        <section className={styles.listSection}>
          <h2 className={styles.sectionTitle}>All Accounts</h2>
          {data.accounts.map((acc, i) => (
            <motion.div
              key={acc.account_id}
              className={styles.accountRow}
              initial={{ opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.06, duration: 0.3 }}
            >
              <div className={styles.accountIcon}>{accountIcon(acc.balance)}</div>
              <div className={styles.accountInfo}>
                <span className={styles.accountName}>{acc.account_id}</span>
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
