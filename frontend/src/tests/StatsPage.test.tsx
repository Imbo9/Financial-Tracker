import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
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
      <StatsPage />
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
});
