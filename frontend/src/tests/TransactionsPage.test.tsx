import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { TransactionsPage } from '../pages/Transactions/TransactionsPage';

const { tx, listMock, taxonomyMock } = vi.hoisted(() => ({
  tx: {
    id: 1, dedup_hash: 'x', booking_date: '2026-07-01T00:00:00Z', amount: -12.5,
    currency: 'EUR', eur_amount: -12.5, description: null, merchant_name: 'Esselunga',
    account_id: null, is_internal: false, category: 'Groceries', subcategory: null,
    status: 'verified' as const, source: 'enable_banking', created_at: '2026-07-01T00:00:00Z',
  },
  listMock: vi.fn(),
  taxonomyMock: vi.fn(),
}));

vi.mock('../api/client', () => ({
  api: {
    transactions: { list: listMock },
    taxonomy: { get: taxonomyMock },
  },
}));

beforeEach(() => {
  listMock.mockReset().mockResolvedValue({ items: [tx], total: 1, page: 1, page_size: 500 });
  taxonomyMock.mockReset().mockResolvedValue({
    expense: { Car: ['Fuel'], Groceries: ['Supermarket'] },
    income: { Salary: [] },
  });
});

function renderAt(entry: string) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/transactions" element={<TransactionsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('TransactionsPage', () => {
  it('fetches the month from the URL anchor', async () => {
    renderAt('/transactions?anchor=2026-06');
    await waitFor(() =>
      expect(listMock).toHaveBeenCalledWith(
        expect.objectContaining({ date_from: '2026-06-01', date_to: '2026-06-30' }),
      ),
    );
    expect(screen.getByText('giugno 2026')).toBeInTheDocument();
  });

  it('defaults to the current month when no anchor is present', async () => {
    renderAt('/transactions');
    // current month bounds are start-of-month .. end-of-month; assert the shape, not a fixed value
    await waitFor(() => expect(listMock).toHaveBeenCalled());
    const arg = listMock.mock.calls[0][0];
    expect(arg.date_from).toMatch(/^\d{4}-\d{2}-01$/);
    expect(arg.date_to).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it('navigates to the next month on the arrow', async () => {
    renderAt('/transactions?anchor=2026-06');
    await waitFor(() => expect(screen.getByText('giugno 2026')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Mese successivo' }));

    await waitFor(() =>
      expect(listMock).toHaveBeenCalledWith(
        expect.objectContaining({ date_from: '2026-07-01', date_to: '2026-07-31' }),
      ),
    );
    expect(screen.getByText('luglio 2026')).toBeInTheDocument();
  });

  it('renders fetched transactions and has no Daily/Monthly toggle', async () => {
    renderAt('/transactions?anchor=2026-07');
    await waitFor(() => expect(screen.getByText('Esselunga')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'Monthly' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Daily' })).not.toBeInTheDocument();
  });

  it('filters within the loaded month via search', async () => {
    listMock.mockResolvedValue({
      items: [
        tx,
        { ...tx, id: 2, merchant_name: 'Q8', category: 'Car' },
      ],
      total: 2, page: 1, page_size: 500,
    });
    renderAt('/transactions?anchor=2026-07');
    await waitFor(() => expect(screen.getByText('Esselunga')).toBeInTheDocument());

    act(() => {
      fireEvent.change(screen.getByPlaceholderText('Search...'), { target: { value: 'Q8' } });
    });
    await waitFor(() => expect(screen.queryByText('Esselunga')).not.toBeInTheDocument());
    expect(screen.getByText('Q8')).toBeInTheDocument();
  });
});
