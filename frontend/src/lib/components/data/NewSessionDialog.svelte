<script lang="ts">
	import { api, type SessionResponse } from '$lib/api/client';

	let {
		sessions,
		onCreated,
		onCancel
	}: {
		sessions: SessionResponse[];
		onCreated: () => void;
		onCancel: () => void;
	} = $props();

	const currentYear = new Date().getFullYear();
	let year = $state(currentYear);
	let season = $state('winter');
	let continueFrom = $state<number | null>(null);
	let creating = $state(false);
	let error = $state('');

	// Category inputs
	let categoryInputs = $state<{ name: string; display_name: string }[]>([]);
	let newCatName = $state('');

	const seasonOptions = ['winter', 'spring', 'summer', 'fall'];

	function addCategory() {
		const name = newCatName.trim();
		if (!name) return;
		if (categoryInputs.some(c => c.name.toLowerCase() === name.toLowerCase())) return;
		categoryInputs = [...categoryInputs, { name: name.toLowerCase().replace(/\s+/g, '_'), display_name: name }];
		newCatName = '';
	}

	function removeCategory(index: number) {
		categoryInputs = categoryInputs.filter((_, i) => i !== index);
	}

	function handleCatKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			e.preventDefault();
			addCategory();
		}
	}

	async function handleCreate() {
		error = '';
		creating = true;
		try {
			const newSession = await api.createSession({
				year,
				season,
				categories: categoryInputs.map(c => ({ name: c.name, display_name: c.display_name })),
				continue_from_session_id: continueFrom ?? undefined
			});
			// Set as active
			await api.updateSession(newSession.id, { is_active: true });
			onCreated();
		} catch (e: unknown) {
			error = e instanceof Error ? e.message : 'Failed to create session';
		}
		creating = false;
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') onCancel();
	}
</script>

<svelte:window onkeydown={handleKeydown} />

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onclick={onCancel} onkeydown={handleKeydown}>
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="mx-4 w-full max-w-lg rounded-xl border border-border bg-card p-6 shadow-lg" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()}>
		<h2 class="text-lg font-semibold">New Session</h2>
		<p class="mt-1 text-sm text-muted-foreground">Create a new tracking session.</p>

		{#if error}
			<div class="mt-3 rounded-md bg-red-500/10 px-3 py-2 text-sm text-red-600">{error}</div>
		{/if}

		<div class="mt-4 space-y-4">
			<div class="grid grid-cols-2 gap-4">
				<div>
					<label for="ns-year" class="block text-sm font-medium text-muted-foreground">Year</label>
					<input
						id="ns-year"
						type="number"
						min="2020"
						max="2030"
						bind:value={year}
						class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
					/>
				</div>
				<div>
					<label for="ns-season" class="block text-sm font-medium text-muted-foreground">Season</label>
					<select
						id="ns-season"
						bind:value={season}
						class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
					>
						{#each seasonOptions as s}
							<option value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
						{/each}
					</select>
				</div>
			</div>

			<div>
				<label for="ns-continue" class="block text-sm font-medium text-muted-foreground">Continue from (copy categories)</label>
				<select
					id="ns-continue"
					bind:value={continueFrom}
					class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
				>
					<option value={null}>None — start fresh</option>
					{#each sessions as s}
						<option value={s.id}>{s.label} ({s.categories.length} categories)</option>
					{/each}
				</select>
			</div>

			<!-- Categories -->
			<div>
				<label class="block text-sm font-medium text-muted-foreground">Categories</label>
				<p class="mt-0.5 text-xs text-muted-foreground">Add categories to track. You can also add more later.</p>

				{#if categoryInputs.length > 0}
					<div class="mt-2 flex flex-wrap gap-1.5">
						{#each categoryInputs as cat, i}
							<span class="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">
								{cat.display_name}
								<button
									onclick={() => removeCategory(i)}
									class="ml-0.5 rounded-full p-0.5 hover:bg-primary/20 transition-colors"
								>
									<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
										<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
									</svg>
								</button>
							</span>
						{/each}
					</div>
				{/if}

				<div class="mt-2 flex items-center gap-2">
					<input
						type="text"
						bind:value={newCatName}
						onkeydown={handleCatKeydown}
						placeholder="e.g. Training, COGS 118C, Research"
						class="flex-1 rounded-md border border-border bg-background px-3 py-1.5 text-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
					/>
					<button
						onclick={addCategory}
						disabled={!newCatName.trim()}
						class="rounded-md border border-border px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted disabled:opacity-40"
					>
						Add
					</button>
				</div>
			</div>
		</div>

		<div class="mt-6 flex justify-end gap-3">
			<button
				onclick={onCancel}
				class="rounded-md px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted"
			>
				Cancel
			</button>
			<button
				onclick={handleCreate}
				disabled={creating}
				class="rounded-md bg-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary/90 disabled:opacity-50"
			>
				{creating ? 'Creating...' : 'Create Session'}
			</button>
		</div>
	</div>
</div>
