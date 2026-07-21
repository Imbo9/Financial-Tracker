export type Granularity = 'week' | 'month' | 'year';

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

function ymd(d: Date): string {
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
}

// All math is done in UTC to avoid the host timezone shifting day boundaries.
function mondayOf(isoDate: string): Date {
  const d = new Date(`${isoDate}T00:00:00Z`);
  const dow = d.getUTCDay(); // 0=Sun .. 6=Sat
  const toMonday = dow === 0 ? -6 : 1 - dow;
  d.setUTCDate(d.getUTCDate() + toMonday);
  return d;
}

function isValidAnchor(g: Granularity, anchor: string): boolean {
  if (g === 'year') return /^\d{4}$/.test(anchor);
  if (g === 'month') {
    if (!/^\d{4}-\d{2}$/.test(anchor)) return false;
    const m = Number(anchor.slice(5, 7));
    return m >= 1 && m <= 12;
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(anchor)) return false;
  const t = new Date(`${anchor}T00:00:00Z`).getTime();
  return !Number.isNaN(t);
}

export function periodBounds(g: Granularity, anchor: string): { from: string; to: string } {
  if (g === 'week') {
    const mon = mondayOf(anchor);
    const sun = new Date(mon);
    sun.setUTCDate(mon.getUTCDate() + 6);
    return { from: ymd(mon), to: ymd(sun) };
  }
  if (g === 'month') {
    const [y, m] = anchor.split('-').map(Number);
    return { from: `${y}-${pad(m)}-01`, to: ymd(new Date(Date.UTC(y, m, 0))) };
  }
  const y = Number(anchor);
  return { from: `${y}-01-01`, to: `${y}-12-31` };
}

export function shiftPeriod(g: Granularity, anchor: string, delta: 1 | -1): string {
  if (g === 'week') {
    const mon = mondayOf(anchor);
    mon.setUTCDate(mon.getUTCDate() + 7 * delta);
    return ymd(mon);
  }
  if (g === 'month') {
    const [y, m] = anchor.split('-').map(Number);
    const d = new Date(Date.UTC(y, m - 1 + delta, 1));
    return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}`;
  }
  return String(Number(anchor) + delta);
}

export function formatPeriodLabel(g: Granularity, anchor: string): string {
  if (g === 'year') return anchor;
  if (g === 'month') {
    const [y, m] = anchor.split('-').map(Number);
    return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString('it-IT', {
      month: 'long',
      year: 'numeric',
      timeZone: 'UTC',
    });
  }
  const { from, to } = periodBounds('week', anchor);
  const dayMon = (iso: string) =>
    new Date(`${iso}T00:00:00Z`).toLocaleDateString('it-IT', {
      day: 'numeric',
      month: 'short',
      timeZone: 'UTC',
    });
  return `${dayMon(from)} – ${dayMon(to)} ${to.slice(0, 4)}`;
}

export function currentAnchor(g: Granularity): string {
  const now = new Date();
  const y = now.getUTCFullYear();
  const m = now.getUTCMonth() + 1;
  if (g === 'week') return ymd(mondayOf(ymd(now)));
  if (g === 'month') return `${y}-${pad(m)}`;
  return String(y);
}

export function parsePeriodParams(
  granularity: string | null,
  anchor: string | null,
): { granularity: Granularity; anchor: string } {
  const g: Granularity | null =
    granularity === 'week' || granularity === 'month' || granularity === 'year' ? granularity : null;
  if (!g || !anchor || !isValidAnchor(g, anchor)) {
    return { granularity: 'month', anchor: currentAnchor('month') };
  }
  return { granularity: g, anchor: g === 'week' ? ymd(mondayOf(anchor)) : anchor };
}
