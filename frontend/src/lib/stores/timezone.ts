/**
 * Timezone store + formatting helpers.
 *
 * All clock times shown in the UI are formatted in this timezone (the
 * default — America/Los_Angeles — survives until the user picks a different
 * one in Settings). The store is hydrated once at app start from
 * GET /api/settings; writes back via PUT /api/settings/timezone.
 *
 * Timestamps in the DB are stored in UTC (timer_service uses datetime.utcnow);
 * dates (YYYY-MM-DD) on entries are local to the chosen timezone.
 */

import { writable, get } from 'svelte/store';

export const DEFAULT_TIMEZONE = 'America/Los_Angeles';

export const timezone = writable<string>(DEFAULT_TIMEZONE);

/** A small curated list. Users can pick "Other…" and the dropdown gracefully accepts any IANA tz. */
export const COMMON_TIMEZONES: { id: string; label: string }[] = [
	{ id: 'America/Los_Angeles', label: 'Los Angeles (PT)' },
	{ id: 'America/Denver',      label: 'Denver (MT)' },
	{ id: 'America/Chicago',     label: 'Chicago (CT)' },
	{ id: 'America/New_York',    label: 'New York (ET)' },
	{ id: 'America/Anchorage',   label: 'Anchorage (AKT)' },
	{ id: 'Pacific/Honolulu',    label: 'Honolulu (HT)' },
	{ id: 'Europe/London',       label: 'London' },
	{ id: 'Europe/Paris',        label: 'Paris / Berlin / Madrid' },
	{ id: 'Asia/Shanghai',       label: 'Shanghai / Beijing' },
	{ id: 'Asia/Tokyo',          label: 'Tokyo' },
	{ id: 'Asia/Kolkata',        label: 'Kolkata (IST)' },
	{ id: 'Australia/Sydney',    label: 'Sydney' },
	{ id: 'UTC',                 label: 'UTC' },
];

/** Format an ISO string (UTC or with offset) as "h:mm AM/PM" in the given tz.
 *
 * SQLite's `datetime('now')` returns naive UTC text like "2026-05-26 08:25:00"
 * (no Z, no offset). The ECMAScript spec parses such strings as **local time**,
 * which would convert "UTC 8:25" to whatever timezone the JS runtime is in —
 * an ~7-hour offset bug in PDT. We normalise here: if a string lacks a tz
 * designator, treat it as UTC (matches SQLite + Python datetime conventions).
 */
export function formatTimeIn(tz: string, iso: string | null | undefined): string {
	if (!iso) return '';
	try {
		return new Date(normalizeAsUtc(iso)).toLocaleTimeString(undefined, {
			hour: 'numeric',
			minute: '2-digit',
			timeZone: tz,
		});
	} catch {
		return '';
	}
}

/** Append `Z` to naive timestamp strings ("2026-05-26 08:25:00") so JS reads
 * them as UTC instead of local. Strings that already carry a timezone (Z or
 * ±HH:MM) are returned unchanged. */
export function normalizeAsUtc(iso: string): string {
	// Already has a timezone designator? Leave it alone.
	if (/[Zz]$|[+-]\d{2}:?\d{2}$/.test(iso)) return iso;
	// SQLite naive format is "YYYY-MM-DD HH:MM:SS" — swap the space for T to
	// make it ISO-shaped, then append Z to mark as UTC.
	return iso.replace(' ', 'T') + 'Z';
}

/** YYYY-MM-DD in the given tz. Uses Intl rather than Date arithmetic to dodge DST. */
export function ymdInTz(tz: string, date: Date = new Date()): string {
	const parts = new Intl.DateTimeFormat('en-CA', {
		timeZone: tz,
		year: 'numeric',
		month: '2-digit',
		day: '2-digit',
	}).formatToParts(date);
	const y = parts.find((p) => p.type === 'year')?.value ?? '1970';
	const m = parts.find((p) => p.type === 'month')?.value ?? '01';
	const d = parts.find((p) => p.type === 'day')?.value ?? '01';
	return `${y}-${m}-${d}`;
}

/** Hour-of-day (0-23) in the given tz right now. Used by the late-night prompt. */
export function hourInTz(tz: string, date: Date = new Date()): number {
	const parts = new Intl.DateTimeFormat('en-US', {
		timeZone: tz,
		hour: 'numeric',
		hour12: false,
	}).formatToParts(date);
	const h = parts.find((p) => p.type === 'hour')?.value;
	const n = h ? parseInt(h, 10) : 0;
	// "24" sometimes appears in some locales for midnight — normalise to 0.
	return n === 24 ? 0 : n;
}

/** Snapshot accessor for non-Svelte callers. */
export function currentTz(): string {
	return get(timezone);
}

/** Build a UTC ISO timestamp from local (YYYY-MM-DD, HH, MM) in the named tz.
 *
 * Uses Intl to derive the tz offset for the wall-clock instant (DST-aware) and
 * inverts it. Returns an ISO string like "2026-05-27T00:55:00.000Z".
 */
export function localDateTimeToUtcIso(
	ymd: string,
	hours: number,
	minutes: number,
	tz: string,
): string {
	const h = String(Math.max(0, Math.min(23, Math.floor(hours)))).padStart(2, '0');
	const m = String(Math.max(0, Math.min(59, Math.floor(minutes)))).padStart(2, '0');
	// Treat the wall-clock components as if they were UTC, then derive the
	// offset for the chosen tz at that instant and subtract it.
	const fakeUtc = new Date(`${ymd}T${h}:${m}:00Z`);
	const parts = Object.fromEntries(
		new Intl.DateTimeFormat('en-US', {
			timeZone: tz,
			year: 'numeric', month: '2-digit', day: '2-digit',
			hour: '2-digit', minute: '2-digit', second: '2-digit',
			hour12: false,
		}).formatToParts(fakeUtc).map((p) => [p.type, p.value]),
	);
	const hh = parts.hour === '24' ? '00' : parts.hour;
	const rendered = new Date(`${parts.year}-${parts.month}-${parts.day}T${hh}:${parts.minute}:${parts.second}Z`);
	const offset = rendered.getTime() - fakeUtc.getTime();
	return new Date(fakeUtc.getTime() - offset).toISOString();
}

/** Inverse: an ISO string → "HH:MM" in the named tz. Used to populate edit forms. */
export function isoToLocalHHMM(iso: string | null | undefined, tz: string): string {
	if (!iso) return '';
	try {
		const d = new Date(iso);
		const parts = Object.fromEntries(
			new Intl.DateTimeFormat('en-US', {
				timeZone: tz,
				hour: '2-digit',
				minute: '2-digit',
				hour12: false,
			}).formatToParts(d).map((p) => [p.type, p.value]),
		);
		const hh = parts.hour === '24' ? '00' : parts.hour;
		return `${hh}:${parts.minute}`;
	} catch {
		return '';
	}
}
