<script lang="ts">
	import type { ChatApprovalResponse } from '$lib/api/client';
	import { approveQuery, rejectQuery } from '$lib/stores/chat';

	let { approval }: { approval: ChatApprovalResponse } = $props();
	let approving = $state(false);
	let showTools = $state(false);

	const info = $derived(approval.context_info);
	// In tool-use mode the backend packs the tool names into categories_included.
	const tools = $derived(info.categories_included || []);

	async function handleApprove() {
		approving = true;
		await approveQuery(approval.approval_id);
		approving = false;
	}
</script>

<div class="mx-auto mb-3 max-w-lg">
	<div class="rounded-xl border border-border bg-card p-4 shadow-sm">
		<div class="mb-3 flex items-center gap-2">
			<div class="flex h-6 w-6 items-center justify-center rounded-full bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
				<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
				</svg>
			</div>
			<span class="text-sm font-medium">Send this to Claude?</span>
		</div>

		<p class="mb-3 text-xs text-muted-foreground leading-relaxed">
			{info.context_preview || 'Claude will use its tools to query your database directly.'}
		</p>

		<!-- Tool inventory disclosure -->
		{#if tools.length > 0}
			<button
				onclick={() => (showTools = !showTools)}
				class="mb-3 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
			>
				<svg class="h-3 w-3 transition-transform {showTools ? 'rotate-90' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
				</svg>
				{tools.length} read-only tools available
			</button>
			{#if showTools}
				<ul class="mb-3 flex flex-wrap gap-1.5">
					{#each tools as t}
						<li class="rounded-full bg-muted px-2 py-0.5 font-mono text-[10px] text-muted-foreground">{t}</li>
					{/each}
				</ul>
			{/if}
		{/if}

		<div class="flex gap-2">
			<button
				onclick={handleApprove}
				disabled={approving}
				class="flex-1 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
			>
				{approving ? 'Working…' : 'Send to Claude'}
			</button>
			<button
				onclick={() => rejectQuery()}
				disabled={approving}
				class="rounded-lg border border-border px-4 py-2 text-sm font-medium text-muted-foreground hover:bg-muted disabled:opacity-50 transition-colors"
			>
				Cancel
			</button>
		</div>
	</div>
</div>
