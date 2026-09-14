/**
 * Shared "viewing date" store.
 *
 * The Recorder (and anything else that browses a single day) reads the selected
 * day (YYYY-MM-DD) from here. It lives at module scope so it SURVIVES in-app
 * navigation — pick a past day, hop to the Planner and back, and you stay on
 * that day instead of snapping to today.
 *
 * It is intentionally in-memory only (not persisted to localStorage): a full app
 * reload resets it to today, which is the safe default.
 *
 * Midnight rollover: the store follows `todayYMD` as long as the user is
 * actually looking at today. Leave the app open overnight (or wake the machine
 * the next morning) and the view advances to the new day on its own — no
 * remount required. A deliberately pinned past day is left alone.
 */

import { writable, get } from 'svelte/store';
import { todayYMD, todayYMDNow } from './clock';

export const viewDate = writable<string>(todayYMDNow());

// `following` is recomputed on every write: selecting today (or "Back to today")
// re-arms the follow, selecting any other day pins the view.
let currentToday = todayYMDNow();
let following = true;

viewDate.subscribe((d) => {
	following = d === currentToday;
});

// Never unsubscribed — one app-lifetime heartbeat, which is the point.
todayYMD.subscribe((t) => {
	if (t === currentToday) return;
	currentToday = t;
	if (following) viewDate.set(t);
});

/** The live current day, re-exported so callers need only one import. */
export { todayYMD };

/** Jump the view back to today and re-arm the follow. */
export function goToToday(): void {
	viewDate.set(get(todayYMD));
}
