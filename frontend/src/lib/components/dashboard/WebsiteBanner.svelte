<script lang="ts">
	import { onMount } from 'svelte';

	const STORAGE_KEY = 'logger:website-banner-dismissed';
	const WEBSITE_URL = 'https://kbian.org/logger-website/';

	let dismissed = $state(true);

	onMount(() => {
		dismissed = localStorage.getItem(STORAGE_KEY) === 'true';
	});

	function dismiss() {
		localStorage.setItem(STORAGE_KEY, 'true');
		dismissed = true;
	}
</script>

{#if !dismissed}
	<div class="relative overflow-hidden rounded-xl border border-primary/20 bg-gradient-to-r from-primary/5 via-primary/[0.03] to-transparent px-4 py-3 sm:px-5">
		<div class="flex items-center justify-between gap-4">
			<div class="flex items-center gap-3 min-w-0">
				<div class="shrink-0 rounded-lg bg-primary/10 p-1.5">
					<svg class="h-4 w-4 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
					</svg>
				</div>
				<div class="min-w-0">
					<div class="text-sm font-medium">
						New to log(ger)?
						<a
							href={WEBSITE_URL}
							target="_blank"
							rel="noopener"
							class="ml-1 text-primary underline-offset-2 hover:underline"
						>
							See the feature tour
						</a>
					</div>
					<div class="text-xs text-muted-foreground">
						Workflows, screenshots, and how Groups → Families → Categories fit together.
					</div>
				</div>
			</div>
			<button
				onclick={dismiss}
				aria-label="Dismiss"
				class="shrink-0 rounded-md p-1 text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground"
			>
				<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
				</svg>
			</button>
		</div>
	</div>
{/if}
