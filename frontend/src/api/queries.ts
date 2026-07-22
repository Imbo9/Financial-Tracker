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
  categories: (date_from: string, date_to: string, direction: 'income' | 'expense' = 'expense') => ({
    queryKey: ['stats', 'categories', date_from, date_to, direction] as const,
    queryFn: () => api.stats.categories({ date_from, date_to, direction }),
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
    date_from: string,
    date_to: string,
    direction: 'income' | 'expense' = 'expense',
  ) => ({
    queryKey: ['stats', 'subcategories', category, date_from, date_to, direction] as const,
    queryFn: () => api.stats.subcategories({ category, date_from, date_to, direction }),
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
  create: () => ({
    mutationKey: ['accounts', 'create'] as const,
    mutationFn: api.accounts.create,
  }),
  update: () => ({
    mutationKey: ['accounts', 'update'] as const,
    mutationFn: api.accounts.update,
  }),
  remove: () => ({
    mutationKey: ['accounts', 'remove'] as const,
    mutationFn: api.accounts.remove,
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
