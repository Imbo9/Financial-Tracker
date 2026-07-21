import { describe, expect, it } from 'vitest';
import {
  periodBounds, shiftPeriod, formatPeriodLabel, currentAnchor, parsePeriodParams,
} from '../lib/period';

describe('periodBounds', () => {
  it('month spans first to last day', () => {
    expect(periodBounds('month', '2026-06')).toEqual({ from: '2026-06-01', to: '2026-06-30' });
  });
  it('february in a leap year ends on the 29th', () => {
    expect(periodBounds('month', '2028-02')).toEqual({ from: '2028-02-01', to: '2028-02-29' });
  });
  it('year spans Jan 1 to Dec 31', () => {
    expect(periodBounds('year', '2026')).toEqual({ from: '2026-01-01', to: '2026-12-31' });
  });
  it('week runs Monday to Sunday from a Monday anchor', () => {
    expect(periodBounds('week', '2026-07-06')).toEqual({ from: '2026-07-06', to: '2026-07-12' });
  });
});

describe('shiftPeriod', () => {
  it('month rolls over December to January', () => {
    expect(shiftPeriod('month', '2026-12', 1)).toBe('2027-01');
  });
  it('month rolls back January to December', () => {
    expect(shiftPeriod('month', '2026-01', -1)).toBe('2025-12');
  });
  it('year steps by one', () => {
    expect(shiftPeriod('year', '2026', 1)).toBe('2027');
  });
  it('week steps 7 days and can cross a month boundary', () => {
    expect(shiftPeriod('week', '2026-06-29', 1)).toBe('2026-07-06');
  });
  it('week can cross a year boundary', () => {
    expect(shiftPeriod('week', '2026-12-28', 1)).toBe('2027-01-04');
  });
});

describe('formatPeriodLabel', () => {
  it('month is the Italian month name and year', () => {
    expect(formatPeriodLabel('month', '2026-06')).toBe('giugno 2026');
  });
  it('year is the bare year', () => {
    expect(formatPeriodLabel('year', '2026')).toBe('2026');
  });
  it('week shows both day/month ends and the year once', () => {
    expect(formatPeriodLabel('week', '2026-07-06')).toBe('6 lug – 12 lug 2026');
  });
});

describe('parsePeriodParams', () => {
  it('defaults to the current month on missing params', () => {
    const out = parsePeriodParams(null, null);
    expect(out.granularity).toBe('month');
    expect(out.anchor).toBe(currentAnchor('month'));
  });
  it('defaults on an unknown granularity', () => {
    expect(parsePeriodParams('banana', '2026-06').granularity).toBe('month');
  });
  it('defaults on a malformed anchor for the granularity', () => {
    expect(parsePeriodParams('month', 'not-a-date').anchor).toBe(currentAnchor('month'));
  });
  it('normalises a non-Monday week anchor to that week\'s Monday', () => {
    // 2026-07-09 is a Thursday; its Monday is 2026-07-06
    expect(parsePeriodParams('week', '2026-07-09')).toEqual({ granularity: 'week', anchor: '2026-07-06' });
  });
  it('rejects a day-overflow week anchor instead of coercing it (2026-02-30)', () => {
    // JS would parse 2026-02-30 as a valid ISO date and roll it to Mar 2 — the gate
    // must fall back to the current month, not silently show the wrong week.
    const out = parsePeriodParams('week', '2026-02-30');
    expect(out.granularity).toBe('month');
    expect(out.anchor).toBe(currentAnchor('month'));
  });
  it('passes a valid month through unchanged', () => {
    expect(parsePeriodParams('month', '2026-06')).toEqual({ granularity: 'month', anchor: '2026-06' });
  });
});

describe('currentAnchor', () => {
  it('month anchor is YYYY-MM shaped', () => {
    expect(currentAnchor('month')).toMatch(/^\d{4}-\d{2}$/);
  });
  it('year anchor is YYYY shaped', () => {
    expect(currentAnchor('year')).toMatch(/^\d{4}$/);
  });
  it('week anchor is a Monday (YYYY-MM-DD)', () => {
    const a = currentAnchor('week');
    expect(a).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(new Date(`${a}T00:00:00Z`).getUTCDay()).toBe(1); // Monday
  });
});
