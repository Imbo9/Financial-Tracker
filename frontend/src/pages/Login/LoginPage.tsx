import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../api/client';
import styles from './LoginPage.module.css';

export function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const result = await api.auth.login({ username, password });
      if (result.ok) {
        navigate('/transactions', { replace: true });
      } else {
        setError('Credenziali non valide');
      }
    } catch {
      setError('Credenziali non valide');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.backdrop} />
      <div className={styles.container}>
        <div className={styles.header}>
          <h1 className={styles.title}>Ledger</h1>
          <div className={styles.subtitle}>Financial Gateway</div>
        </div>

        <form className={styles.form} onSubmit={handleSubmit}>
          <div className={styles.fieldGroup}>
            <label htmlFor="username" className={styles.label}>
              Username
            </label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              className={styles.input}
              autoComplete="username"
              required
              placeholder=" "
            />
            <div className={styles.underline} />
          </div>

          <div className={styles.fieldGroup}>
            <label htmlFor="password" className={styles.label}>
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              className={styles.input}
              autoComplete="current-password"
              required
              placeholder=" "
            />
            <div className={styles.underline} />
          </div>

          {error && (
            <div className={styles.errorContainer}>
              <p className={styles.error}>{error}</p>
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !username || !password}
            className={styles.button}
          >
            <span className={styles.buttonText}>
              {loading ? 'Accesso…' : 'Accedi'}
            </span>
            {loading && <div className={styles.spinner} />}
          </button>
        </form>

        <div className={styles.footer}>
          <div className={styles.line} />
          <p className={styles.footerText}>Secure authentication</p>
          <div className={styles.line} />
        </div>
      </div>
    </div>
  );
}
