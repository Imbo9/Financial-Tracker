import { Navigate, Outlet } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Sidebar } from './Sidebar';
import { BottomNav } from './BottomNav';
import { authQueries } from '../api/queries';
import styles from '../App.module.css';

export function ProtectedRoute() {
  const { isPending, isError } = useQuery({ ...authQueries.me() });

  if (isPending) return null;
  if (isError) return <Navigate to="/login" replace />;

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
