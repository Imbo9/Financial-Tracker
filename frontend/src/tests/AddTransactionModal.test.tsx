import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { AddTransactionModal } from '../pages/Transactions/AddTransactionModal';

vi.mock('../api/client', () => ({
  api: {
    taxonomy: {
      get: vi.fn().mockResolvedValue({
        expense: { Groceries: ['Supermarket'], Car: ['Fuel', 'Tolls & Parking'] },
        income: { Salary: ['Base salary'] },
      }),
    },
    transactions: { create: vi.fn().mockResolvedValue({}) },
  },
}));

function renderModal() {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <AddTransactionModal onClose={() => {}} onAdd={() => {}} />
    </QueryClientProvider>,
  );
}

describe('AddTransactionModal', () => {
  it('shows expense categories by default and income ones after the toggle', async () => {
    renderModal();
    await waitFor(() =>
      expect(screen.getByRole('option', { name: 'Car' })).toBeInTheDocument(),
    );
    expect(screen.queryByRole('option', { name: 'Salary' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Income' }));
    await waitFor(() =>
      expect(screen.getByRole('option', { name: 'Salary' })).toBeInTheDocument(),
    );
    expect(screen.queryByRole('option', { name: 'Car' })).not.toBeInTheDocument();
  });

  it('populates subcategories for the chosen category and resets on change', async () => {
    renderModal();
    await waitFor(() =>
      expect(screen.getByRole('option', { name: 'Car' })).toBeInTheDocument(),
    );

    fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'Car' } });
    expect(await screen.findByLabelText('Subcategory')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Fuel' })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Subcategory'), { target: { value: 'Fuel' } });
    fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'Groceries' } });
    expect(screen.queryByRole('option', { name: 'Fuel' })).not.toBeInTheDocument();
    expect((screen.getByLabelText('Subcategory') as HTMLSelectElement).value).toBe('');
  });
});
