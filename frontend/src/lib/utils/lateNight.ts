/**
 * Late-night date attribution helpers.
 *
 * When the local clock is between midnight and the cutoff hour (default 5am),
 * we surface a "Today / Yesterday" prompt on entry-create and entry-edit flows
 * so the user can decide which calendar day a session of work belongs to.
 *
 * "Late night" is a local-clock concept, not a UTC one. We use the user's
 * machine clock directly.
 */

const DEFAULT_CUTOFF_HOUR = 5;

/** YYYY-MM-DD in the local timezone. */
export function formatLocalYMD(d: Date): string {
	const y = d.getFullYear();
	const m = String(d.getMonth() + 1).padStart(2, '0');
	const day = String(d.getDate()).padStart(2, '0');
	return `${y}-${m}-${day}`;
}

/** Is the given moment within the late-night window (00:00 ≤ hour < cutoff)? */
export function isLateNight(now: Date = new Date(), cutoffHour: number = DEFAULT_CUTOFF_HOUR): boolean {
	const h = now.getHours();
	return h >= 0 && h < cutoffHour;
}

/** {today, yesterday} as YYYY-MM-DD strings in local time. */
export function lateNightDateOptions(now: Date = new Date()): { today: string; yesterday: string } {
	const today = formatLocalYMD(now);
	const y = new Date(now);
	y.setDate(y.getDate() - 1);
	return { today, yesterday: formatLocalYMD(y) };
}

/** A readable label for a YYYY-MM-DD date, e.g. "Mon, May 25". */
export function shortDateLabel(ymd: string): string {
	// Parse as local time (NOT UTC) to avoid timezone-shift display bugs.
	const [y, m, d] = ymd.split('-').map(Number);
	const dt = new Date(y, m - 1, d);
	return dt.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
}
