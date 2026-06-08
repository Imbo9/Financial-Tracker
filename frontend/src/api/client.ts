import axios from 'axios';
import type { Transaction, TransactionsResponse, CategoryStat, MonthlyStat, TransactionFilters, AccountsResponse } from './types';

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
const TOKEN   = import.meta.env.VITE_API_TOKEN ?? '';

const http = axios.create({
  baseURL: BASE_URL,
  headers: { 'x-webhook-secret': TOKEN },
});

export const api = {
  transactions: {
    list: (filters: TransactionFilters = {}): Promise<TransactionsResponse> =>
      http.get('/transactions', { params: filters }).then(r => r.data),

    create: (data: Partial<Transaction>): Promise<Transaction> =>
      http.post('/transactions', data).then(r => r.data),

    update: (id: number, data: Partial<Transaction>): Promise<Transaction> =>
      http.patch(`/transactions/${id}`, data).then(r => r.data),

    delete: (id: number): Promise<void> =>
      http.delete(`/transactions/${id}`).then(r => r.data),
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

// Mock data for development (used when API is unreachable)
export const MOCK_TRANSACTIONS: Transaction[] = [
  { id: 1, dedup_hash: 'a1', booking_date: '2026-06-08T10:30:00Z', amount: -4.27, currency: 'USD', eur_amount: -4.0, description: 'Medium membership', merchant_name: 'Medium', account_id: 'revolut-main', is_internal: false, category: 'Career & Professional', subcategory: 'Professional subscriptions', status: 'verified', source: 'enable_banking', created_at: '2026-06-08T10:30:00Z' },
  { id: 2, dedup_hash: 'a2', booking_date: '2026-06-07T09:00:00Z', amount: -7.99, currency: 'EUR', eur_amount: -7.99, description: 'Iliad mobile', merchant_name: 'Iliad', account_id: 'revolut-main', is_internal: false, category: 'Connectivity', subcategory: 'Mobile phone', status: 'verified', source: 'enable_banking', created_at: '2026-06-07T09:00:00Z' },
  { id: 3, dedup_hash: 'a3', booking_date: '2026-06-05T14:20:00Z', amount: 50.0, currency: 'EUR', eur_amount: 50.0, description: 'Transfer from Rosalia', merchant_name: 'Rosalia', account_id: 'revolut-main', is_internal: false, category: 'Income', subcategory: null, status: 'verified', source: 'tasker', created_at: '2026-06-05T14:20:00Z' },
  { id: 4, dedup_hash: 'a4', booking_date: '2026-06-04T12:00:00Z', amount: -12.50, currency: 'EUR', eur_amount: -12.50, description: 'Costa Coffee', merchant_name: 'Costa Coffee', account_id: 'revolut-main', is_internal: false, category: 'Eating Out', subcategory: 'Coffee', status: 'verified', source: 'enable_banking', created_at: '2026-06-04T12:00:00Z' },
  { id: 5, dedup_hash: 'a5', booking_date: '2026-06-03T18:45:00Z', amount: -89.99, currency: 'EUR', eur_amount: -89.99, description: 'Zalando purchase', merchant_name: 'Zalando', account_id: 'revolut-main', is_internal: false, category: 'Personal shopping', subcategory: 'Clothing', status: 'verified', source: 'enable_banking', created_at: '2026-06-03T18:45:00Z' },
  { id: 6, dedup_hash: 'a6', booking_date: '2026-06-02T08:15:00Z', amount: -3.50, currency: 'EUR', eur_amount: -3.50, description: 'Bar San Marco', merchant_name: 'Bar San Marco', account_id: 'revolut-main', is_internal: false, category: 'Eating Out', subcategory: 'Coffee', status: 'verified', source: 'enable_banking', created_at: '2026-06-02T08:15:00Z' },
  { id: 7, dedup_hash: 'a7', booking_date: '2026-06-01T16:00:00Z', amount: 2198.80, currency: 'EUR', eur_amount: 2198.80, description: 'Stipendio Giugno', merchant_name: 'Employer', account_id: 'revolut-main', is_internal: false, category: 'Income', subcategory: 'Salary', status: 'verified', source: 'enable_banking', created_at: '2026-06-01T16:00:00Z' },
];

export const MOCK_CATEGORY_STATS: CategoryStat[] = [
  { category: 'Connectivity',         total: 7.99,  count: 1, percentage: 7.0  },
  { category: 'Career & Professional', total: 4.27,  count: 1, percentage: 3.7  },
  { category: 'Eating Out',           total: 16.00, count: 2, percentage: 14.0 },
  { category: 'Personal shopping',    total: 89.99, count: 1, percentage: 78.5 },
  { category: 'Other',                total: 5.00,  count: 2, percentage: 4.4  },
];

export const MOCK_MONTHLY_STATS: MonthlyStat[] = [
  { month: '2026-01', income: 0,       expenses: 0,      net: 0 },
  { month: '2026-02', income: 0,       expenses: 0,      net: 0 },
  { month: '2026-03', income: 0,       expenses: 0,      net: 0 },
  { month: '2026-04', income: 55708,   expenses: 86.65,  net: 55622 },
  { month: '2026-05', income: 2198.80, expenses: 1454.75, net: 744.05 },
  { month: '2026-06', income: 50,      expenses: 114.25, net: -64.25 },
];
