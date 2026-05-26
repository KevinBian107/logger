import { writable } from 'svelte/store';
import { browser } from '$app/environment';

type Theme = 'light' | 'dark' | 'system';

// Default to light — users on systems with dark-mode set system-wide were getting
// the dark app even though most of the UI is tuned for light. Settings still lets
// them switch to dark or system at any time.
const DEFAULT_THEME: Theme = 'light';

function getInitialTheme(): Theme {
	if (!browser) return DEFAULT_THEME;
	const stored = localStorage.getItem('theme') as Theme | null;
	// One-time migration: when the default flipped from 'system' to 'light',
	// users who never explicitly picked a theme were stuck on whatever their OS
	// preferred. Treat unset OR the old 'system' fallback as "no choice made"
	// and use the new default. Explicit 'light' / 'dark' choices are kept.
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
