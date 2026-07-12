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
