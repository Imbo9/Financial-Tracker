import { useNavigate } from 'react-router-dom';
import { api } from '../../api/client';
import styles from './MorePage.module.css';

const SETTINGS = [
  { label: 'Sync now',        sub: 'Force an Enable Banking sync',    icon: '↻', accent: true },
  { label: 'Categories',      sub: 'Manage and rename categories',    icon: '⊞' },
  { label: 'Notifications',   sub: 'Telegram alert settings',         icon: '◎' },
  { label: 'Export data',     sub: 'Download transactions as CSV',    icon: '↓' },
  { label: 'About',           sub: 'Version, licenses',               icon: '◑' },
];

export function MorePage() {
  const navigate = useNavigate();

  const handleLogout = async () => {
    await api.auth.logout();
    navigate('/login', { replace: true });
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>More</h1>
      </header>
      <main className={styles.main}>
        <div className={styles.statusCard}>
          <div className={styles.statusRow}>
            <span className={styles.statusLabel}>API</span>
            <span className={styles.statusBadge}>Connected</span>
          </div>
          <div className={styles.statusRow}>
            <span className={styles.statusLabel}>Last sync</span>
            <span className={styles.statusValue}>Today · 12:00</span>
          </div>
          <div className={styles.statusRow}>
            <span className={styles.statusLabel}>Next sync</span>
            <span className={styles.statusValue}>Today · 18:00</span>
          </div>
          <div className={styles.statusRow}>
            <span className={styles.statusLabel}>Source</span>
            <span className={styles.statusValue}>Revolut IT · Enable Banking</span>
          </div>
        </div>

        <div className={styles.menuSection}>
          {SETTINGS.map(s => (
            <button key={s.label} className={`${styles.menuItem} ${s.accent ? styles.menuAccent : ''}`}>
              <span className={styles.menuIcon}>{s.icon}</span>
              <div className={styles.menuText}>
                <span className={styles.menuLabel}>{s.label}</span>
                <span className={styles.menuSub}>{s.sub}</span>
              </div>
              <span className={styles.menuChevron}>›</span>
            </button>
          ))}
        </div>

        <button className={styles.logoutButton} onClick={handleLogout}>Esci</button>
      </main>
    </div>
  );
}
