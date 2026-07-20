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
    await waitFor(() =>
      expect(categoriesMock).toHaveBeenCalledWith({ days_back: 30, direction: 'expense' }),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Income' }));

    await waitFor(() =>
      expect(categoriesMock).toHaveBeenCalledWith({ days_back: 30, direction: 'income' }),
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
});
