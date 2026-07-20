import { api } from './client';
import type { TransactionFilters } from './types';

export const authQueries = {
  me: () => ({
    queryKey: ['auth', 'me'] as const,
    queryFn: api.auth.me,
    retry: false,
  }),
};

export const transactionQueries = {
  list: (filters: TransactionFilters = {}) => ({
    queryKey: ['transactions', filters] as const,
    queryFn: () => api.transactions.list(filters),
  }),
  create: () => ({
    mutationKey: ['transactions', 'create'] as const,
    mutationFn: api.transactions.create,
  }),
};

export const statsQueries = {
  categories: (days_back = 30, direction: 'income' | 'expense' = 'expense') => ({
    queryKey: ['stats', 'categories', days_back, direction] as const,
    queryFn: () => api.stats.categories({ days_back, direction }),
  }),
  monthly: (months = 12) => ({
    queryKey: ['stats', 'monthly', months] as const,
    queryFn: () => api.stats.monthly({ months }),
  }),
  balanceHistory: (months = 12) => ({
    queryKey: ['stats', 'balance-history', months] as const,
    queryFn: () => api.stats.balanceHistory({ months }),
  }),
  subcategories: (
    category: string,
    days_back = 30,
    direction: 'income' | 'expense' = 'expense',
  ) => ({
    queryKey: ['stats', 'subcategories', category, days_back, direction] as const,
    queryFn: () => api.stats.subcategories({ category, days_back, direction }),
  }),
  categoryTrend: (
    category: string,
    months = 12,
    direction: 'income' | 'expense' = 'expense',
    subcategory?: string,
  ) => ({
    // subcategory is part of the key so picking a chip refetches only this query
    queryKey: ['stats', 'category-trend', category, months, direction, subcategory ?? null] as const,
    queryFn: () => api.stats.categoryTrend({ category, months, direction, subcategory }),
  }),
};

export const accountQueries = {
  list: () => ({
    queryKey: ['accounts'] as const,
    queryFn: api.accounts.list,
  }),
};

export const taxonomyQueries = {
  categories: () => ({
    queryKey: ['taxonomy'] as const,
    queryFn: api.taxonomy.get,
    staleTime: Infinity,
    gcTime: Infinity,
  }),
};
