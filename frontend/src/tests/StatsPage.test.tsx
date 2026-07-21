import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { StatsPage } from '../pages/Stats/StatsPage';

const { categoriesMock } = vi.hoisted(() => ({
  categoriesMock: vi.fn().mockResolvedValue([]),
}));

vi.mock('../api/client', () => ({
  api: {
    stats: {
      categories: categoriesMock,
      monthly: vi.fn().mockResolvedValue([]),
    },
  },
}));

function renderPage() {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <StatsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('StatsPage', () => {
  it('fetches income categories when the Income tab is clicked', async () => {
    renderPage();
    // No period params in the URL → resolves to the default current month (dates vary by run day).
    await waitFor(() =>
      expect(categoriesMock).toHaveBeenCalledWith(expect.objectContaining({ direction: 'expense' })),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Income' }));

    await waitFor(() =>
      expect(categoriesMock).toHaveBeenCalledWith(expect.objectContaining({ direction: 'income' })),
    );
  });

  it('navigates to the category drill-down when a legend item is clicked', async () => {
    categoriesMock.mockResolvedValue([
      { category: 'Eating Out', total: 50, count: 2, percentage: 100 },
    ]);
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <MemoryRouter initialEntries={['/stats']}>
          <Routes>
            <Route path="/stats" element={<StatsPage />} />
            <Route
              path="/stats/category/:category"
              element={<div>detail-for-Eating Out</div>}
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.getByText('Eating Out')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Eating Out/ }));

    await waitFor(() =>
      expect(screen.getByText('detail-for-Eating Out')).toBeInTheDocument(),
    );
  });

  it('drives the categories query from the period in the URL and navigates on next', async () => {
    categoriesMock.mockResolvedValue([]);
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <MemoryRouter initialEntries={['/stats?granularity=month&anchor=2026-06']}>
          <Routes>
            <Route path="/stats" element={<StatsPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // June 2026 → the categories call carries that month's bounds
    await waitFor(() =>
      expect(categoriesMock).toHaveBeenCalledWith(
        expect.objectContaining({ date_from: '2026-06-01', date_to: '2026-06-30' }),
      ),
    );

    // the label reflects the period, and clicking next moves to July
    expect(screen.getByText('giugno 2026')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Periodo successivo' }));
    await waitFor(() =>
      expect(categoriesMock).toHaveBeenCalledWith(
        expect.objectContaining({ date_from: '2026-07-01', date_to: '2026-07-31' }),
      ),
    );
  });
});
