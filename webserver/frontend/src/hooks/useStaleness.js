import { useEffect, useState } from 'react';

/**
 * Returns the current Date.now() value, updated every `intervalMs` milliseconds.
 * Used to drive periodic re-renders for staleness checks even when no new
 * messages have arrived.
 */
export function useNowTick(intervalMs = 1000) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => {
      setNow(Date.now());
    }, intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);

  return now;
}

/**
 * Determine if a message freshness timestamp (Unix epoch seconds, preferably
 * backend receipt time) is stale relative to `nowMs` (Date.now() value) given a
 * stale timeout in milliseconds.
 *
 * Returns false when the timestamp is missing/invalid so callers don't flag
 * "no data ever received" as stale (those tiles already render as "--").
 */
export function isTimestampStale(timestampSeconds, nowMs, staleTimeoutMs) {
  if (typeof timestampSeconds !== 'number' || !isFinite(timestampSeconds) || timestampSeconds <= 0) {
    return false;
  }
  if (!staleTimeoutMs || staleTimeoutMs <= 0) return false;
  const ageMs = nowMs - timestampSeconds * 1000;
  return ageMs > staleTimeoutMs;
}

/**
 * Receipt time is the reliability anchor for freshness checks. Driver or bus
 * timestamps may be device uptime, monotonic ticks, or another host's clock.
 */
export function messageFreshnessTimestamp(message) {
  const receivedAt = typeof message?.received_at === 'number' ? message.received_at : null;
  if (receivedAt !== null && isFinite(receivedAt) && receivedAt > 0) return receivedAt;

  const timestamp = typeof message?.timestamp === 'number' ? message.timestamp : null;
  return timestamp !== null && isFinite(timestamp) && timestamp > 0 ? timestamp : null;
}

/**
 * Returns the freshest (max) receipt/fallback timestamp from a list of messages,
 * in seconds.
 * Returns null if no valid timestamps are present.
 */
export function freshestTimestamp(messages) {
  let max = -Infinity;
  for (const msg of messages) {
    const t = messageFreshnessTimestamp(msg);
    if (t !== null && t > max) max = t;
  }
  return max === -Infinity ? null : max;
}
