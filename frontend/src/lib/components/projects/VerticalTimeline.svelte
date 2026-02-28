<script lang="ts">
	import type { ResearchSessionEntry } from '$lib/api/client';

	let {
		sessions,
		familyColor,
		hasApiKey,
		onGenerate
	}: {
		sessions: ResearchSessionEntry[];
		familyColor: string | null;
		hasApiKey: boolean;
		onGenerate: (sessionId: number) => void;
	} = $props();

	let generatingIds = $state<Set<number>>(new Set());

	function formatHours(minutes: number): string {
		const h = Math.floor(minutes / 60);
		const m = minutes % 60;
		if (h === 0) return `${m}m`;
		if (m === 0) return `${h}h`;
		return `${h}h ${m}m`;
	}

	function sessionLabel(s: ResearchSessionEntry): string {
		return s.session_label || `${s.season.charAt(0).toUpperCase() + s.season.slice(1)} ${s.year}`;
	}

	async function handleGenerate(sessionId: number) {
		generatingIds = new Set([...generatingIds, sessionId]);
		try {
			await onGenerate(sessionId);
		} finally {
			const next = new Set(generatingIds);
			next.delete(sessionId);
			generatingIds = next;
		}
	}

	let color = $derived(familyColor || '#6366f1');
</script>

<div class="relative pl-8">
	<!-- Vertical line -->
	<div
		class="absolute left-[11px] top-4 bottom-4 w-0.5"
		style="background-color: {color}; opacity: 0.3;"
	></div>

	{#each sessions as session, i}
		<div class="relative pb-8 last:pb-0">
			<!-- Node circle -->
			<div
				class="absolute left-[-21px] top-4 h-5 w-5 rounded-full border-2 bg-background"
				style="border-color: {color};"
			>
				<div
					class="absolute inset-1 rounded-full"
					style="background-color: {color};"
				></div>
			</div>

			<!-- Arrow between nodes -->
			{#if i < sessions.length - 1}
				<div class="absolute left-[-14px] bottom-2 text-muted-foreground/40">
					<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2.5">
						<path stroke-linecap="round" stroke-linejoin="round" d="M19.5 13.5L12 21m0 0l-7.5-7.5M12 21V3" />
					</svg>
				</div>
			{/if}

			<!-- Content card -->
			<div class="rounded-lg border border-border bg-card p-4">
				<!-- Session header -->
				<div class="flex items-center justify-between">
					<h3 class="text-sm font-semibold">{sessionLabel(session)}</h3>
					<div class="flex items-center gap-3 text-xs text-muted-foreground">
						<span class="font-medium tabular-nums">{formatHours(session.total_minutes)}</span>
						<span>{session.active_days}d</span>
					</div>
				</div>

				<!-- Time bar -->
				<div class="mt-2 h-1.5 w-full rounded-full bg-muted overflow-hidden">
					<div
						class="h-full rounded-full transition-all"
						style="width: {Math.min(100, (session.total_minutes / Math.max(1, ...sessions.map(s => s.total_minutes))) * 100)}%; background-color: {color}; opacity: 0.7;"
					></div>
				</div>

				<!-- Text entries badge -->
				{#if session.text_entries_count > 0}
					<div class="mt-2 text-[11px] text-muted-foreground">
						{session.text_entries_count} log entr{session.text_entries_count === 1 ? 'y' : 'ies'}
					</div>
				{/if}

				<!-- AI Description -->
				<div class="mt-3">
					{#if session.ai_description}
						<div class="rounded-md bg-muted/30 p-3">
							<p class="text-sm leading-relaxed text-foreground/90">{session.ai_description}</p>
						</div>
						<button
							onclick={() => handleGenerate(session.session_id)}
							disabled={generatingIds.has(session.session_id)}
							class="mt-1.5 text-[11px] text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
						>
							{generatingIds.has(session.session_id) ? 'Regenerating...' : 'Regenerate'}
						</button>
					{:else if !hasApiKey}
						<p class="text-xs text-muted-foreground">
							Add API key in <a href="/settings" class="underline font-medium text-foreground">Settings</a> to generate narratives
						</p>
					{:else}
						<button
							onclick={() => handleGenerate(session.session_id)}
							disabled={generatingIds.has(session.session_id)}
							class="flex items-center gap-1.5 rounded-md border border-border bg-muted/30 px-3 py-1.5 text-xs font-medium hover:bg-muted transition-colors disabled:opacity-50"
						>
							{#if generatingIds.has(session.session_id)}
								<svg class="h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24">
									<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
									<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
								</svg>
								Generating...
							{:else}
								<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
									<path stroke-linecap="round" stroke-linejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
								</svg>
								Generate research narrative
							{/if}
						</button>
					{/if}
				</div>
			</div>
		</div>
	{/each}
</div>
