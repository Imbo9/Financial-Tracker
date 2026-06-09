import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Sidebar }          from './components/Sidebar';
import { BottomNav }        from './components/BottomNav';
import { LoginPage }        from './pages/Login/LoginPage';
import { TransactionsPage } from './pages/Transactions/TransactionsPage';
import { StatsPage }        from './pages/Stats/StatsPage';
import { AccountsPage }     from './pages/Accounts/AccountsPage';
import { MorePage }         from './pages/More/MorePage';
import styles from './App.module.css';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/*"
          element={
            <div className={styles.shell}>
              <Sidebar />
              <main className={styles.content}>
                <Routes>
                  <Route path="/"             element={<Navigate to="/transactions" replace />} />
                  <Route path="/transactions" element={<TransactionsPage />} />
                  <Route path="/stats"        element={<StatsPage />} />
                  <Route path="/accounts"     element={<AccountsPage />} />
                  <Route path="/more"         element={<MorePage />} />
                </Routes>
              </main>
              <BottomNav />
            </div>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
