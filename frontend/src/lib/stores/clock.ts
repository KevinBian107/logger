/**
 * Live wall-clock stores — the app's notion of "now", kept honest.
 *
 * Pages used to snapshot `new Date()` when their component initialised, which
 * is right exactly once: leave the Recorder open past midnight (or shut the
 * laptop and reopen it the next morning) and it keeps showing — and logging
 * into — the stale day until something forces a remount.
 *
 * These stores re-check the clock on three triggers:
 *   1. a short interval,
 *   2. window focus / tab visibility — background tabs get their timers
 *      throttled and a sleeping machine stops firing them altogether, so the
 *      interval alone can miss a rollover by hours,
 *   3. a timezone change, since "what day is it" is tz-dependent and the tz
 *      preference hydrates from the backend a beat after boot.
 *
 * `todayYMD` and `currentHour` only notify when their value ACTUALLY changes,
 * so subscribers are safe to read inside an $effect without it re-running on
 * every tick.
 */

import { readable, get } from 'svelte/store';
import { browser } from '$app/environment';
import { timezone, ymdInTz, hourInTz } from './timezone';

const TICK_MS = 20_000;
const NOW_TICK_MS = 30_000;

/** Run `fn` on the shared heartbeat: interval + focus/visibility + tz change. */
function heartbeat(fn: () => void): () => void {
	// Fires immediately with the current tz, which doubles as the initial sync.
	const unsubTz = timezone.subscribe(fn);
	if (!browser) return unsubTz;
	const id = setInterval(fn, TICK_MS);
	const onVisible = () => {
		if (!document.hidden) fn();
	};
	window.addEventListener('focus', fn);
	document.addEventListener('visibilitychange', onVisible);
	return () => {
		clearInterval(id);
		window.removeEventListener('focus', fn);
		document.removeEventListener('visibilitychange', onVisible);
		unsubTz();
	};
}

/** The current calendar day (YYYY-MM-DD) in the active timezone. Rolls over by itself. */
export const todayYMD = readable<string>(ymdInTz(get(timezone)), (set) => {
	let current = ymdInTz(get(timezone));
	set(current);
	return heartbeat(() => {
		const next = ymdInTz(get(timezone));
		if (next === current) return;
		current = next;
		set(next);
	});
});

/** Hour-of-day (0-23) in the active timezone. Drives the greeting. */
export const currentHour = readable<number>(hourInTz(get(timezone)), (set) => {
	let current = hourInTz(get(timezone));
	set(current);
	return heartbeat(() => {
		const next = hourInTz(get(timezone));
		if (next === current) return;
		current = next;
		set(next);
	});
});

/** Epoch millis, refreshed every 30s (and on focus). For live "now" markers. */
export const nowMs = readable<number>(Date.now(), (set) => {
	if (!browser) return;
	const sync = () => set(Date.now());
	const id = setInterval(sync, NOW_TICK_MS);
	const onVisible = () => {
		if (!document.hidden) sync();
	};
	window.addEventListener('focus', sync);
	document.addEventListener('visibilitychange', onVisible);
	return () => {
		clearInterval(id);
		window.removeEventListener('focus', sync);
		document.removeEventListener('visibilitychange', onVisible);
	};
});

/** Snapshot of today for non-reactive callers (avoids start/stop churn on the store). */
export function todayYMDNow(): string {
	return ymdInTz(get(timezone));
}
