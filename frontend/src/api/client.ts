import axios, { type AxiosError } from 'axios';
import type {
  Transaction,
  TransactionsResponse,
  CategoryStat,
  MonthlyStat,
  TransactionFilters,
  AccountsResponse,
} from './types';

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

const http = axios.create({
  baseURL: BASE_URL,
  withCredentials: true,
});

http.interceptors.response.use(
  r => r,
  (err: AxiosError) => {
    if (err.response?.status === 401 && window.location.pathname !== '/login') {
      window.location.href = '/login';
    }
    return Promise.reject(err);
  },
);

export const api = {
  auth: {
    login: (data: { username: string; password: string }): Promise<{ ok: boolean }> =>
      http.post('/auth/login', data).then(r => r.data),

    logout: (): Promise<void> =>
      http.post('/auth/logout').then(() => undefined),
  },

  transactions: {
    list: (filters: TransactionFilters = {}): Promise<TransactionsResponse> =>
      http.get('/transactions', { params: filters }).then(r => r.data),

    create: (data: Partial<Transaction>): Promise<Transaction> =>
      http.post('/transactions', data).then(r => r.data),
  },

  stats: {
    categories: (params: { days_back?: number; direction?: string } = {}): Promise<CategoryStat[]> =>
      http.get('/stats/categories', { params }).then(r => r.data),

    monthly: (params: { months?: number } = {}): Promise<MonthlyStat[]> =>
      http.get('/stats/monthly', { params }).then(r => r.data),
  },

  accounts: {
    list: (): Promise<AccountsResponse> =>
      http.get('/accounts').then(r => r.data),
  },
};
