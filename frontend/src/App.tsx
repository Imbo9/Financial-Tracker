import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ErrorBoundary }    from './components/ErrorBoundary';
import { ProtectedRoute }   from './components/ProtectedRoute';
import { LoginPage }        from './pages/Login/LoginPage';
import { TransactionsPage } from './pages/Transactions/TransactionsPage';
import { StatsPage }        from './pages/Stats/StatsPage';
import { AccountsPage }     from './pages/Accounts/AccountsPage';
import { MorePage }         from './pages/More/MorePage';

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<ProtectedRoute />}>
            <Route index                element={<Navigate to="/transactions" replace />} />
            <Route path="/transactions" element={<TransactionsPage />} />
            <Route path="/stats"        element={<StatsPage />} />
            <Route path="/accounts"     element={<AccountsPage />} />
            <Route path="/more"         element={<MorePage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
