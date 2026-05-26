/**
 * Late-night date attribution helpers, timezone-aware.
 *
 * "Late night" is a local-clock concept in the user's chosen timezone (Settings
 * → Timezone, default America/Los_Angeles). Between 00:00 and the cutoff hour
 * (default 5) we surface a Today/Yesterday prompt on entry-create and edit so
 * the user can pick which calendar day a work session belongs to.
 */

import { get } from 'svelte/store';
import { timezone, hourInTz, ymdInTz, currentTz } from '$lib/stores/timezone';

const DEFAULT_CUTOFF_HOUR = 5;

function tzOrLive(tz?: string): string {
	return tz ?? get(timezone);
}

/** YYYY-MM-DD in the active timezone (default LA, overridable). */
export function formatLocalYMD(d: Date = new Date(), tz?: string): string {
	return ymdInTz(tzOrLive(tz), d);
}

/** Is the given moment within the late-night window (0 ≤ hour < cutoff)? */
export function isLateNight(now: Date = new Date(), cutoffHour: number = DEFAULT_CUTOFF_HOUR, tz?: string): boolean {
	const h = hourInTz(tzOrLive(tz), now);
	return h >= 0 && h < cutoffHour;
}

/** {today, yesterday} as YYYY-MM-DD strings in the active timezone. */
export function lateNightDateOptions(now: Date = new Date(), tz?: string): { today: string; yesterday: string } {
	const z = tzOrLive(tz);
	const today = ymdInTz(z, now);
	// Compute "yesterday" by subtracting one day's worth of ms from `now`, then
	// re-projecting through the timezone (handles DST cleanly).
	const yMs = now.getTime() - 24 * 60 * 60 * 1000;
	const yesterday = ymdInTz(z, new Date(yMs));
	return { today, yesterday };
}

/** Readable label for a YYYY-MM-DD, e.g. "Mon, May 25". Parsed as local date. */
export function shortDateLabel(ymd: string): string {
	const [y, m, d] = ymd.split('-').map(Number);
	const dt = new Date(y, m - 1, d);
	return dt.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
}

// Re-export the tz helpers so callers don't need two imports.
export { currentTz, timezone };
