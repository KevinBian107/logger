import { writable } from 'svelte/store';
import { browser } from '$app/environment';
import { api, type TimerEntryResponse } from '$lib/api/client';

export const activeTimers = writable<TimerEntryResponse[]>([]);

let pollInterval: ReturnType<typeof setInterval> | null = null;

export async function loadActiveTimers() {
	if (!browser) return;
	try {
		const timers = await api.getActiveTimers();
		activeTimers.set(timers);
	} catch {
		// API not available
	}
}

export function startPolling() {
	if (!browser || pollInterval) return;
	loadActiveTimers();
	pollInterval = setInterval(loadActiveTimers, 30_000);
}

export function stopPolling() {
	if (pollInterval) {
		clearInterval(pollInterval);
		pollInterval = null;
	}
}

export async function startTimer(categoryId: number) {
	const timer = await api.startTimer(categoryId);
	await loadActiveTimers();
	return timer;
}

export async function pauseTimer(id: number) {
	const timer = await api.pauseTimer(id);
	await loadActiveTimers();
	return timer;
}

export async function resumeTimer(id: number) {
	const timer = await api.resumeTimer(id);
	await loadActiveTimers();
	return timer;
}

export async function stopTimer(id: number, description?: string, location?: string) {
	const timer = await api.stopTimer(id, description, location);
	await loadActiveTimers();
	return timer;
}

export async function discardTimer(id: number) {
	await api.discardTimer(id);
	await loadActiveTimers();
}

/**
 * Compute elapsed seconds for display, accounting for pauses.
 */
export function computeElapsedSeconds(timer: TimerEntryResponse): number {
	const start = new Date(timer.start_time).getTime();
	const now = Date.now();
	let elapsed = (now - start) / 1000;

	// Subtract completed pause time
	elapsed -= timer.total_paused_seconds;

	// If currently paused, subtract current pause duration
	if (timer.is_paused && timer.pause_start) {
		const pauseStart = new Date(timer.pause_start).getTime();
		elapsed -= (now - pauseStart) / 1000;
	}

	return Math.max(0, Math.floor(elapsed));
}

export function formatElapsed(seconds: number): string {
	const h = Math.floor(seconds / 3600);
	const m = Math.floor((seconds % 3600) / 60);
	const s = seconds % 60;
	return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}
