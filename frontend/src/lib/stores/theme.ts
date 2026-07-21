import { writable } from 'svelte/store';
import { browser } from '$app/environment';

type Theme = 'light' | 'dark' | 'system';

// Default to dark. Settings still lets users switch to light or system at any time.
const DEFAULT_THEME: Theme = 'dark';

function getInitialTheme(): Theme {
	if (!browser) return DEFAULT_THEME;
	const stored = localStorage.getItem('theme') as Theme | null;
	// No stored value, or 'system' (no explicit choice made): use the default.
	// An explicit 'light' or 'dark' pick is always respected.
	if (!stored || stored === 'system') return DEFAULT_THEME;
	return stored;
}

function applyTheme(theme: Theme) {
	if (!browser) return;
	const root = document.documentElement;
	if (theme === 'system') {
		const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
		root.classList.toggle('dark', prefersDark);
	} else {
		root.classList.toggle('dark', theme === 'dark');
	}
}

export const theme = writable<Theme>(getInitialTheme());

if (browser) {
	theme.subscribe((value) => {
		localStorage.setItem('theme', value);
		applyTheme(value);
	});

	// Listen for system theme changes
	window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
		const currentTheme = localStorage.getItem('theme') as Theme;
		if (currentTheme === 'system') {
			applyTheme('system');
		}
	});
}

export function toggleTheme() {
	theme.update((current) => {
		if (current === 'light') return 'dark';
		if (current === 'dark') return 'system';
		return 'light';
	});
}
