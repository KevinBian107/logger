import { writable, get } from 'svelte/store';
import { browser } from '$app/environment';
import {
	api,
	type ChatMessageResponse,
	type ChatApprovalResponse,
	type ChatStatusResponse
} from '$lib/api/client';

const API_BASE = 'http://localhost:8000/api';

export const messages = writable<ChatMessageResponse[]>([]);
export const pendingApproval = writable<ChatApprovalResponse | null>(null);
export const isLoading = writable(false);
export const isStreaming = writable(false);
export const chatStatus = writable<ChatStatusResponse | null>(null);
export const chatError = writable<string | null>(null);

export async function loadChatStatus() {
	if (!browser) return;
	try {
		const status = await api.getChatStatus();
		chatStatus.set(status);
	} catch {
		// API not available
	}
}

export async function loadChatHistory() {
	if (!browser) return;
	try {
		const history = await api.getChatHistory();
		messages.set(history);
	} catch {
		// API not available
	}
}

export async function sendQuery(message: string) {
	chatError.set(null);
	isLoading.set(true);

	// Optimistically add user message
	messages.update((msgs) => [
		...msgs,
		{ id: null, role: 'user', content: message, created_at: new Date().toISOString() }
	]);

	try {
		const approval = await api.sendChatQuery(message);
		pendingApproval.set(approval);
	} catch (e) {
		chatError.set(e instanceof Error ? e.message : 'Failed to send query');
	} finally {
		isLoading.set(false);
	}
}

export async function approveQuery(approvalId: string) {
	chatError.set(null);
	isStreaming.set(true);
	pendingApproval.set(null);

	// Add a placeholder streaming message
	const streamingMsg: ChatMessageResponse = {
		id: null,
		role: 'assistant',
		content: '',
		created_at: new Date().toISOString()
	};
	messages.update((msgs) => [...msgs, streamingMsg]);

	try {
		const res = await fetch(`${API_BASE}/chat/approve`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ approval_id: approvalId })
		});

		if (!res.ok) {
			throw new Error(`HTTP ${res.status}`);
		}

		const reader = res.body?.getReader();
		if (!reader) throw new Error('No response body');

		const decoder = new TextDecoder();
		let buffer = '';

		while (true) {
			const { done, value } = await reader.read();
			if (done) break;

			buffer += decoder.decode(value, { stream: true });
			const lines = buffer.split('\n');
			buffer = lines.pop() || '';

			for (const line of lines) {
				if (!line.startsWith('data: ')) continue;
				const data = line.slice(6).trim();
				if (!data) continue;

				try {
					const event = JSON.parse(data);

					if (event.type === 'token') {
						messages.update((msgs) => {
							const updated = [...msgs];
							const last = updated[updated.length - 1];
							if (last && last.role === 'assistant') {
								updated[updated.length - 1] = {
									...last,
									content: last.content + event.content
								};
							}
							return updated;
						});
					} else if (event.type === 'done') {
						messages.update((msgs) => {
							const updated = [...msgs];
							const last = updated[updated.length - 1];
							if (last && last.role === 'assistant') {
								updated[updated.length - 1] = { ...last, id: event.message_id };
							}
							return updated;
						});
					} else if (event.type === 'error') {
						chatError.set(event.content);
					}
				} catch {
					// Skip malformed JSON
				}
			}
		}
	} catch (e) {
		chatError.set(e instanceof Error ? e.message : 'Streaming failed');
	} finally {
		isStreaming.set(false);
	}
}

export async function rejectQuery() {
	const approval = get(pendingApproval);
	if (!approval) return;

	try {
		await api.rejectChatQuery(approval.approval_id);
	} catch {
		// ignore
	}

	pendingApproval.set(null);
	messages.update((msgs) => [
		...msgs,
		{
			id: null,
			role: 'system',
			content: '[Query cancelled by user]',
			created_at: new Date().toISOString()
		}
	]);
}

export async function clearHistory() {
	try {
		await api.clearChatHistory();
		messages.set([]);
		pendingApproval.set(null);
		chatError.set(null);
	} catch (e) {
		chatError.set(e instanceof Error ? e.message : 'Failed to clear history');
	}
}
