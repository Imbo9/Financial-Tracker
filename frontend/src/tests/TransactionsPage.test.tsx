import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { TransactionsPage } from '../pages/Transactions/TransactionsPage';

// vi.mock factories are hoisted above top-level consts, so the fixture must live
// inside vi.hoisted() — a plain top-level `const tx` throws "Cannot access 'tx'
// before initialization" when the factory below runs.
const { tx } = vi.hoisted(() => ({
  tx: {
    id: 1, dedup_hash: 'x', booking_date: '2026-07-01T00:00:00Z', amount: -12.5,
    currency: 'EUR', eur_amount: -12.5, description: null, merchant_name: 'Esselunga',
    account_id: null, is_internal: false, category: 'Groceries', subcategory: null,
    status: 'verified' as const, source: 'enable_banking', created_at: '2026-07-01T00:00:00Z',
  },
}));

vi.mock('../api/client', () => ({
  api: {
    transactions: {
      list: vi.fn().mockResolvedValue({ items: [tx], total: 1, page: 1, page_size: 500 }),
    },
  },
}));

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <TransactionsPage />
    </QueryClientProvider>,
  );
}

describe('TransactionsPage', () => {
  it('renders fetched transactions', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('Esselunga')).toBeInTheDocument());
    // Robust vs the plan's getByText(/12\.50/): the summary <AnimatedNumber> can also
    // reach "12.50", which would make a single-match query throw. The tx row always
    // renders it synchronously, so at-least-one match is deterministic.
    expect(screen.getAllByText(/12[.,]50/).length).toBeGreaterThan(0);
  });
});
