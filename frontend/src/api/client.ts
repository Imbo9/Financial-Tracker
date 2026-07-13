import axios, { type AxiosError, type AxiosResponse } from 'axios';
import type {
  Transaction,
  TransactionsResponse,
  CategoryStat,
  MonthlyStat,
  TransactionFilters,
  AccountsResponse,
  Taxonomy,
  BalancePoint,
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

// Backend wraps every response in { data: ... } — unwrap once here.
const unwrap = <T>(r: AxiosResponse<{ data: T }>): T => r.data.data;

export const api = {
  auth: {
    login: (data: { username: string; password: string }): Promise<{ ok: boolean }> =>
      http.post('/v1/auth/login', data).then(unwrap<{ ok: boolean }>),
    logout: (): Promise<void> => http.post('/v1/auth/logout').then(() => undefined),
    me: (): Promise<{ username: string }> =>
      http.get('/v1/auth/me').then(unwrap<{ username: string }>),
  },
  transactions: {
    list: (filters: TransactionFilters = {}): Promise<TransactionsResponse> =>
      http.get('/v1/transactions', { params: filters }).then(unwrap<TransactionsResponse>),
    create: (data: Partial<Transaction>): Promise<Transaction> =>
      http.post('/v1/transactions', data).then(unwrap<Transaction>),
  },
  stats: {
    categories: (
      params: { days_back?: number; direction?: 'income' | 'expense' } = {},
    ): Promise<CategoryStat[]> =>
      http.get('/v1/stats/categories', { params }).then(unwrap<CategoryStat[]>),
    monthly: (params: { months?: number } = {}): Promise<MonthlyStat[]> =>
      http.get('/v1/stats/monthly', { params }).then(unwrap<MonthlyStat[]>),
    balanceHistory: (params: { months?: number } = {}): Promise<BalancePoint[]> =>
      http.get('/v1/stats/balance-history', { params }).then(unwrap<BalancePoint[]>),
  },
  taxonomy: {
    get: (): Promise<Taxonomy> =>
      http.get('/v1/categories').then(unwrap<Taxonomy>),
  },
  accounts: {
    list: (): Promise<AccountsResponse> =>
      http.get('/v1/accounts').then(unwrap<AccountsResponse>),
  },
};
