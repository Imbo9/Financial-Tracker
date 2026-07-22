import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { AccountModal } from '../pages/Accounts/AccountModal';

vi.mock('../api/client', () => ({
  api: {
    accounts: {
      create: vi.fn().mockResolvedValue({}),
      update: vi.fn().mockResolvedValue({}),
    },
  },
}));

function renderModal(props: Partial<Parameters<typeof AccountModal>[0]> = {}) {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <AccountModal onClose={() => {}} onSaved={() => {}} account={null} {...props} />
    </QueryClientProvider>,
  );
}

describe('AccountModal', () => {
  it('creates a manual account with type and opening balance', async () => {
    const { api } = await import('../api/client');
    renderModal();
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Wallet' } });
    fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'cash' } });
    fireEvent.change(screen.getByLabelText('Opening balance'), { target: { value: '200' } });
    fireEvent.click(screen.getByRole('button', { name: /Save/i }));
    const createMock = api.accounts.create as ReturnType<typeof vi.fn>;
    await waitFor(() => expect(createMock).toHaveBeenCalled());
    // TanStack Query v5's mutationFn is invoked as (variables, mutationFnContext) —
    // assert on the payload (first arg) rather than the full call signature.
    expect(createMock.mock.calls[0][0]).toEqual(
      expect.objectContaining({ display_name: 'Wallet', type: 'cash', opening_balance: 200 }),
    );
  });

  it('hides the opening-balance field when editing a synced (EB) account', () => {
    renderModal({
      account: {
        account_id: 'eb1', balance: 10, display_name: 'Revolut', type: 'bank',
        currency: 'EUR', is_manual: false, opening_balance: 10,
      },
    });
    expect(screen.queryByLabelText('Opening balance')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Name')).toBeInTheDocument();
  });
});
