import { useEffect, useState } from 'react';
import { Navigate, Outlet } from 'react-router-dom';
import { Sidebar }   from './Sidebar';
import { BottomNav } from './BottomNav';
import { api } from '../api/client';
import styles from '../App.module.css';

export function ProtectedRoute() {
  const [status, setStatus] = useState<'checking' | 'ok' | 'unauth'>('checking');

  useEffect(() => {
    api.transactions
      .list({ page_size: 1 })
      .then(() => setStatus('ok'))
      .catch(() => setStatus('unauth'));
  }, []);

  if (status === 'checking') return null;
  if (status === 'unauth')   return <Navigate to="/login" replace />;

  return (
    <div className={styles.shell}>
      <Sidebar />
      <main className={styles.content}>
        <Outlet />
      </main>
      <BottomNav />
    </div>
  );
}
