import React, { useEffect, useState } from 'react';

export function LiveClock() {
  const [now, setNow] = useState<Date | null>(null);

  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  if (!now) return null;

  let hours = now.getHours();
  const ampm = hours >= 12 ? 'PM' : 'AM';
  hours = hours % 12 || 12;
  const minutes = now.getMinutes().toString().padStart(2, '0');
  const seconds = now.getSeconds().toString().padStart(2, '0');
  const dateStr = now.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });

  return (
    <div className="clock-display">
      <span className="digit">{hours.toString().padStart(2, '0')}</span>
      <span className="colon">:</span>
      <span className="digit">{minutes}</span>
      <span className="sec">{seconds}</span>
      <span className="ampm">{ampm}</span>
      <span className="date">{dateStr}</span>
    </div>
  );
}
