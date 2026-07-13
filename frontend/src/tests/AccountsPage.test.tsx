import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { AccountsPage } from '../pages/Accounts/AccountsPage';

vi.mock('../api/client', () => ({
  api: {
    accounts: {
      list: vi.fn().mockResolvedValue({
        assets: 150.0,
        liabilities: 0,
        accounts: [{ account_id: 'uid-1', balance: 150.0, display_name: 'Revolut Main' }],
      }),
    },
    stats: {
      balanceHistory: vi.fn().mockResolvedValue([
        { month: '2026-06', balance: 100.0 },
        { month: '2026-07', balance: 150.0 },
      ]),
    },
  },
}));

function renderPage() {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <AccountsPage />
    </QueryClientProvider>,
  );
}

describe('AccountsPage', () => {
  it('renders the balance history section', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('Balance')).toBeInTheDocument());
  });

  it('shows display_name when present, uid otherwise', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('Revolut Main')).toBeInTheDocument());
    expect(screen.queryByText('uid-1')).not.toBeInTheDocument();
  });
});
