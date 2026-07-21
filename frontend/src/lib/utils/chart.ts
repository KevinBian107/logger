/** Shared chart utilities: palette, formatters, theme colors, resize helper. */

export const PALETTE = [
	'#3B82F6', '#EF4444', '#10B981', '#F59E0B', '#8B5CF6',
	'#EC4899', '#06B6D4', '#F97316', '#6366F1', '#14B8A6',
	'#A855F7', '#D946EF', '#84CC16', '#0EA5E9', '#22C55E',
];

// Deterministic hash-based palette for category/family names, shared by the
// Dashboard breakdown bar, Today's Timeline, and the Planner so the same
// category always renders the same color everywhere.
const CATEGORY_PALETTE = [
	'#6366F1', '#10B981', '#F59E0B', '#EF4444',
	'#A855F7', '#06B6D4', '#EC4899', '#84CC16',
	'#3B82F6', '#F97316', '#14B8A6', '#D946EF',
];

export function colorForCategory(name: string | null | undefined): string {
	const k = (name || '·').trim();
	let h = 0;
	for (let i = 0; i < k.length; i++) {
		h = ((h << 5) - h + k.charCodeAt(i)) | 0;
	}
	return CATEGORY_PALETTE[Math.abs(h) % CATEGORY_PALETTE.length];
}

export function formatHoursMinutes(minutes: number): string {
	const h = Math.floor(minutes / 60);
	const m = minutes % 60;
	if (h === 0) return `${m}m`;
	if (m === 0) return `${h}h`;
	return `${h}h ${m}m`;
}

export interface ThemeColors {
	bg: string;
	fg: string;
	border: string;
	muted: string;
	primary: string;
}

export function getThemeColors(el: HTMLElement): ThemeColors {
	const cs = getComputedStyle(el);
	return {
		bg: cs.getPropertyValue('--color-card').trim() || '#ffffff',
		fg: cs.getPropertyValue('--color-foreground').trim() || '#0f172a',
		border: cs.getPropertyValue('--color-border').trim() || '#e2e8f0',
		muted: cs.getPropertyValue('--color-muted-foreground').trim() || '#64748b',
		primary: cs.getPropertyValue('--color-primary').trim() || '#3B82F6',
	};
}

/**
 * Creates a debounced ResizeObserver that calls `callback(width, height)` on resize.
 * Returns a cleanup function.
 */
export function observeResize(
	el: HTMLElement,
	callback: (width: number, height: number) => void,
	debounceMs = 200,
): () => void {
	let timer: ReturnType<typeof setTimeout> | null = null;

	const observer = new ResizeObserver(() => {
		if (timer) clearTimeout(timer);
		timer = setTimeout(() => {
			const rect = el.getBoundingClientRect();
			const w = Math.floor(rect.width);
			const h = Math.floor(rect.height);
			if (w > 0 && h > 0) callback(w, h);
		}, debounceMs);
	});

	observer.observe(el);

	return () => {
		observer.disconnect();
		if (timer) clearTimeout(timer);
	};
}
