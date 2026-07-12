export interface Transaction {
  id: number;
  dedup_hash: string;
  booking_date: string;
  amount: number;
  currency: string;
  eur_amount: number;
  description: string | null;
  merchant_name: string | null;
  account_id: string | null;
  is_internal: boolean;
  category: string | null;
  subcategory: string | null;
  status: 'pending' | 'verified';
  source: string;
  created_at: string;
}

export interface CategoryStat {
  category: string;
  total: number;
  count: number;
  percentage: number;
}

export interface MonthlyStat {
  month: string;
  income: number;
  expenses: number;
  net: number;
}

export interface AccountBalance {
  account_id: string;
  balance: number;
}

export interface AccountsResponse {
  assets: number;
  liabilities: number;
  accounts: AccountBalance[];
}

export interface TransactionsResponse {
  items: Transaction[];
  total: number;
  page: number;
  page_size: number;
}

export interface TransactionFilters {
  page?: number;
  page_size?: number;
  days_back?: number;
  category?: string;
  direction?: 'income' | 'expense';
  search?: string;
}

export interface Taxonomy {
  expense: Record<string, string[]>;
  income: Record<string, string[]>;
}
