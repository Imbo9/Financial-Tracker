import { useEffect, useRef, useState } from 'react';

interface Props {
  value: number;
  decimals?: number;
  prefix?: string;
  suffix?: string;
  duration?: number;
  className?: string;
}

export function AnimatedNumber({ value, decimals = 2, prefix = '', suffix = '', duration = 800, className }: Props) {
  const [display, setDisplay] = useState(0);
  const displayRef = useRef(0);
  const frameRef = useRef<number>(0);
  const startRef = useRef<number>(0);
  const fromRef  = useRef<number>(0);

  useEffect(() => {
    fromRef.current = displayRef.current;
    startRef.current = 0;
    cancelAnimationFrame(frameRef.current);

    const animate = (ts: number) => {
      if (!startRef.current) startRef.current = ts;
      const progress = Math.min((ts - startRef.current) / duration, 1);
      // Ease out expo
      const eased = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress);
      const next = fromRef.current + (value - fromRef.current) * eased;
      displayRef.current = next;
      setDisplay(next);
      if (progress < 1) frameRef.current = requestAnimationFrame(animate);
    };

    frameRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frameRef.current);
  }, [value, duration]);

  const sign = display < 0 ? '-' : '';
  const formatted = Math.abs(display).toLocaleString('it-IT', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });

  return (
    <span className={className}>
      {sign}{prefix}{formatted}{suffix}
    </span>
  );
}
