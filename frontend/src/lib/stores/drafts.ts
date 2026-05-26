/**
 * Form draft stores — preserve in-progress form input across in-app navigation.
 *
 * Stores live at module scope so they survive component unmount/remount.
 * Use these for any form whose state would be annoying to lose on a quick
 * tab switch (Manual Entry, NewSessionDialog, etc.).
 */

import { writable } from 'svelte/store';

export interface ManualEntryDraft {
	categoryId: number | null;
	date: string;
	hours: number;
	minutes: number;
	description: string;
	location: string;
}

export const EMPTY_MANUAL_ENTRY_DRAFT: ManualEntryDraft = {
	categoryId: null,
	date: '',
	hours: 0,
	minutes: 0,
	description: '',
	location: '',
};

export const manualEntryDraft = writable<ManualEntryDraft>({ ...EMPTY_MANUAL_ENTRY_DRAFT });

export function resetManualEntryDraft() {
	manualEntryDraft.set({ ...EMPTY_MANUAL_ENTRY_DRAFT });
}
