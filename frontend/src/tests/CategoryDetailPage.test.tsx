import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { CategoryDetailPage } from '../pages/CategoryDetail/CategoryDetailPage';

const { subcategoriesMock, trendMock, listMock } = vi.hoisted(() => ({
  subcategoriesMock: vi.fn(),
  trendMock: vi.fn(),
  listMock: vi.fn(),
}));

vi.mock('../api/client', () => ({
  api: {
    stats: { subcategories: subcategoriesMock, categoryTrend: trendMock },
    transactions: { list: listMock },
  },
}));

beforeEach(() => {
  subcategoriesMock.mockReset().mockResolvedValue([
    { subcategory: 'Fuel', total: 75, count: 3, percentage: 75 },
    { subcategory: 'Tolls & Parking', total: 25, count: 1, percentage: 25 },
  ]);
  trendMock.mockReset().mockResolvedValue([
    { month: '2026-06', total: 40 },
    { month: '2026-07', total: 60 },
  ]);
  listMock.mockReset().mockResolvedValue({
    items: [
      {
        id: 1, dedup_hash: 'h', booking_date: '2026-07-02T00:00:00Z', amount: -20,
        currency: 'EUR', eur_amount: -20, description: null, merchant_name: 'Q8',
        account_id: 'a', is_internal: false, category: 'Car', subcategory: 'Fuel',
        status: 'verified', source: 'enable_banking', created_at: '2026-07-02T00:00:00Z',
      },
    ],
    total: 1, page: 1, page_size: 20,
  });
});

function renderPage() {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter initialEntries={['/stats/category/Car?direction=expense']}>
        <Routes>
          <Route path="/stats/category/:category" element={<CategoryDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('CategoryDetailPage', () => {
  it('renders all three sections for the category', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('Car')).toBeInTheDocument());
    expect(screen.getByText('12-Month Trend')).toBeInTheDocument();
    // Subcategory chips load async (TanStack Query batches updates via setTimeout(0),
    // a macrotask) — must waitFor, not a bare assert, or this races the mocked fetch.
    await waitFor(() => expect(screen.getByText('Fuel')).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText('Q8')).toBeInTheDocument());
  });

  it('refetches trend and transactions narrowed to a chosen subcategory', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('Fuel')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /Fuel/ }));

    await waitFor(() =>
      expect(trendMock).toHaveBeenCalledWith(
        expect.objectContaining({ category: 'Car', subcategory: 'Fuel' }),
      ),
    );
    expect(listMock).toHaveBeenCalledWith(
      expect.objectContaining({ category: 'Car', subcategory: 'Fuel' }),
    );
    // the breakdown is category-scoped, so a chip must not invalidate it
    expect(subcategoriesMock).toHaveBeenCalledTimes(1);
  });

  it('surfaces a subcategories load error instead of hiding the section', async () => {
    subcategoriesMock.mockRejectedValue(new Error('boom'));
    renderPage();

    // Regression guard: gating the whole section on data.length would swallow this
    // banner, because data is [] on failure — the section would vanish silently.
    await waitFor(() =>
      expect(screen.getByText(/Impossibile caricare le sottocategorie/)).toBeInTheDocument(),
    );
  });

  it('inherits the period from the URL for the breakdown and transaction queries', async () => {
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <MemoryRouter
          initialEntries={['/stats/category/Car?direction=expense&granularity=month&anchor=2026-06']}
        >
          <Routes>
            <Route path="/stats/category/:category" element={<CategoryDetailPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() =>
      expect(subcategoriesMock).toHaveBeenCalledWith(
        expect.objectContaining({ category: 'Car', date_from: '2026-06-01', date_to: '2026-06-30' }),
      ),
    );
    expect(listMock).toHaveBeenCalledWith(
      expect.objectContaining({ category: 'Car', date_from: '2026-06-01', date_to: '2026-06-30' }),
    );
  });
});
