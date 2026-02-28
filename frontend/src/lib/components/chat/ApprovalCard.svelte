<script lang="ts">
	import type { ChatApprovalResponse } from '$lib/api/client';
	import { approveQuery, rejectQuery } from '$lib/stores/chat';

	let { approval }: { approval: ChatApprovalResponse } = $props();
	let showPreview = $state(false);
	let approving = $state(false);

	const info = $derived(approval.context_info);

	async function handleApprove() {
		approving = true;
		await approveQuery(approval.approval_id);
		approving = false;
	}
</script>

<div class="mx-auto mb-3 max-w-lg">
	<div class="rounded-xl border border-border bg-card p-4 shadow-sm">
		<div class="mb-3 flex items-center gap-2">
			<div class="flex h-6 w-6 items-center justify-center rounded-full bg-amber-100 text-amber-700">
				<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
				</svg>
			</div>
			<span class="text-sm font-medium">Review before sending to Claude</span>
		</div>

		<!-- Summary -->
		<p class="mb-3 text-xs text-muted-foreground">{info.summary}</p>

		<!-- Details grid -->
		<div class="mb-3 grid grid-cols-2 gap-2 text-xs">
			<div class="rounded-lg bg-muted/50 px-3 py-2">
				<span class="text-muted-foreground">Sessions</span>
				<p class="mt-0.5 font-medium">{info.sessions_included.length}</p>
			</div>
			<div class="rounded-lg bg-muted/50 px-3 py-2">
				<span class="text-muted-foreground">Categories</span>
				<p class="mt-0.5 font-medium">{info.categories_included.length}</p>
			</div>
			<div class="rounded-lg bg-muted/50 px-3 py-2">
				<span class="text-muted-foreground">Date range</span>
				<p class="mt-0.5 font-medium">
					{info.date_range[0] ?? 'N/A'} — {info.date_range[1] ?? 'N/A'}
				</p>
			</div>
			<div class="rounded-lg bg-muted/50 px-3 py-2">
				<span class="text-muted-foreground">Data points</span>
				<p class="mt-0.5 font-medium">{info.data_points}</p>
			</div>
		</div>

		<!-- Sessions list -->
		{#if info.sessions_included.length > 0}
			<div class="mb-3">
				<p class="mb-1 text-xs font-medium text-muted-foreground">Sessions included:</p>
				<div class="flex flex-wrap gap-1">
					{#each info.sessions_included as session}
						<span class="rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">{session}</span>
					{/each}
				</div>
			</div>
		{/if}

		<!-- Collapsible preview -->
		{#if info.context_preview}
			<button
				onclick={() => (showPreview = !showPreview)}
				class="mb-3 flex w-full items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
			>
				<svg
					class="h-3 w-3 transition-transform {showPreview ? 'rotate-90' : ''}"
					fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"
				>
					<path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
				</svg>
				Preview context data
			</button>
			{#if showPreview}
				<div class="mb-3 max-h-48 overflow-y-auto rounded-lg bg-muted/30 p-3 text-xs font-mono whitespace-pre-wrap">
					{info.context_preview}
				</div>
			{/if}
		{/if}

		<!-- Action buttons -->
		<div class="flex gap-2">
			<button
				onclick={handleApprove}
				disabled={approving}
				class="flex-1 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
			>
				{approving ? 'Sending...' : 'Send to Claude'}
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
