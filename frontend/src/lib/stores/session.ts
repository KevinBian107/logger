import { writable } from 'svelte/store';
import { browser } from '$app/environment';
import { api, type SessionResponse } from '$lib/api/client';

export const activeSession = writable<SessionResponse | null>(null);
export const sessions = writable<SessionResponse[]>([]);

export async function loadSessions() {
	if (!browser) return;
	try {
		const data = await api.getSessions();
		sessions.set(data.sessions);
	} catch {
		// API not available yet
	}
}

export async function loadActiveSession() {
	if (!browser) return;
	try {
		const data = await api.getActiveSession();
		activeSession.set(data);
	} catch {
		// API not available yet
	}
}
