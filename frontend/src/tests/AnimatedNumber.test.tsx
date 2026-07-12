import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AnimatedNumber } from '../components/AnimatedNumber';

describe('AnimatedNumber', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  // Deterministic rAF: each frame jumps 1000ms, past the 800ms default duration,
  // so the animation settles on the target value after two callbacks.
  function stubAnimationFrames() {
    let now = 0;
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      now += 1000;
      const ts = now;
      setTimeout(() => cb(ts), 0);
      return ts;
    });
    vi.stubGlobal('cancelAnimationFrame', () => {});
  }

  it('keeps the minus sign for negative values', async () => {
    stubAnimationFrames();
    render(<AnimatedNumber value={-914.85} prefix="€ " decimals={2} />);
    await waitFor(() => expect(screen.getByText('-€ 914,85')).toBeInTheDocument());
  });

  it('shows positive values without a sign', async () => {
    stubAnimationFrames();
    render(<AnimatedNumber value={914.85} prefix="€ " decimals={2} />);
    await waitFor(() => expect(screen.getByText('€ 914,85')).toBeInTheDocument());
  });
});
