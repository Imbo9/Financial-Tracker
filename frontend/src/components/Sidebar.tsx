import { NavLink } from 'react-router-dom';
import styles from './Sidebar.module.css';

const NAV = [
  { to: '/transactions', label: 'Transactions', icon: <TxIcon /> },
  { to: '/stats',        label: 'Stats',        icon: <StatsIcon /> },
  { to: '/accounts',    label: 'Accounts',     icon: <AccountsIcon /> },
  { to: '/more',        label: 'More',         icon: <MoreIcon /> },
];

export function Sidebar() {
  return (
    <nav className={styles.sidebar}>
      <div className={styles.logo}>
        <span className={styles.logoMark}>◈</span>
        <span className={styles.logoText}>Imbook</span>
      </div>
      <ul className={styles.nav}>
        {NAV.map(({ to, label, icon }) => (
          <li key={to}>
            <NavLink to={to} className={({ isActive }) => `${styles.link} ${isActive ? styles.active : ''}`}>
              <span className={styles.icon}>{icon}</span>
              <span className={styles.label}>{label}</span>
            </NavLink>
          </li>
        ))}
      </ul>
      <div className={styles.footer}>
        <span className={styles.dot} />
        <span className={styles.footerText}>Live sync on</span>
      </div>
    </nav>
  );
}

function TxIcon()       { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/><path d="M9 12h6M9 16h4"/></svg>; }
function StatsIcon()    { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M18 20V10M12 20V4M6 20v-6"/></svg>; }
function AccountsIcon() { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5"/><path d="M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3"/></svg>; }
function MoreIcon()     { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="5" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="19" r="1"/></svg>; }
