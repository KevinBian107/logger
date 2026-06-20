/**
 * Shared "viewing date" store.
 *
 * The Dashboard and Timer pages both let you look at a specific day. This store
 * holds that selected day (YYYY-MM-DD) at module scope so it SURVIVES in-app
 * navigation — pick a past day on the Dashboard, hop to the Timer page and back,
 * and you stay on that day instead of snapping to today.
 *
 * It is intentionally in-memory only (not persisted to localStorage): a full app
 * reload resets it to today, which is the safe default — you never come back the
 * next day and silently log into a stale past date.
 */

import { writable } from 'svelte/store';
import { formatLocalYMD } from '$lib/utils/lateNight';

export const viewDate = writable<string>(formatLocalYMD(new Date()));
