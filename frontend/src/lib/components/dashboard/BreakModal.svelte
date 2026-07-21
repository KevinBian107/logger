<script lang="ts">
	import BreakPanel from '$lib/components/timer/BreakPanel.svelte';

	let {
		presetDate,
		onChanged = () => {},
		onClose,
	}: {
		presetDate: string;
		onChanged?: () => void;
		onClose: () => void;
	} = $props();

	function handleBackdrop(e: MouseEvent) {
		if (e.target === e.currentTarget) onClose();
	}

	function handleKey(e: KeyboardEvent) {
		if (e.key === 'Escape') onClose();
	}
</script>

<svelte:window onkeydown={handleKey} />

<div
	role="presentation"
	onclick={handleBackdrop}
	class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm"
>
	<div class="w-full max-w-md rounded-xl border border-border bg-card shadow-2xl">
		<div class="flex items-center justify-between border-b border-border px-5 py-3">
			<div>
				<h3 class="text-base font-semibold">Breaks</h3>
				<p class="mt-0.5 text-xs text-muted-foreground">Mark rest days — they never break your streak.</p>
			</div>
			<button
				onclick={onClose}
				class="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
				aria-label="Close"
			>
				<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
				</svg>
			</button>
		</div>

		<div class="max-h-[70vh] overflow-y-auto px-5 py-4">
			<BreakPanel {presetDate} {onChanged} />
		</div>
	</div>
</div>
