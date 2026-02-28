<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type SessionResponse, type FamilyResponse } from '$lib/api/client';

	let { session, onUpdate }: { session: SessionResponse; onUpdate?: () => void } = $props();

	let families = $state<FamilyResponse[]>([]);
	let editingCatId = $state<number | null>(null);
	let savingCatId = $state<number | null>(null);

	// New family creation
	let creatingFamily = $state(false);
	let newFamilyName = $state('');
	let newFamilyType = $state('research');

	// Add category
	let addingCategory = $state(false);
	let newCatName = $state('');
	let addingCatLoading = $state(false);
	let addCatError = $state('');

	// Track selected group for the editing row
	let editGroup = $state<string>('');
	let editFamilyId = $state<number>(0);

	const GROUP_LABELS: Record<string, string> = {
		research: 'Research',
		course: 'Courses',
		personal: 'Personal',
		other: 'Other',
	};

	const GROUP_COLORS: Record<string, string> = {
		research: 'bg-blue-500/10 text-blue-700',
		course: 'bg-purple-500/10 text-purple-700',
		personal: 'bg-amber-500/10 text-amber-700',
		other: 'bg-gray-500/10 text-gray-600',
	};

	async function loadFamilies() {
		try {
			families = await api.getFamilies();
		} catch { /* */ }
	}

	// Families filtered by selected group
	const familiesForGroup = $derived(
		editGroup ? families.filter(f => (f.family_type || 'other') === editGroup) : []
	);

	// All unique group types from families
	const availableGroups = $derived.by(() => {
		const types = new Set<string>();
		for (const f of families) types.add(f.family_type || 'other');
		return ['research', 'course', 'personal', 'other'].filter(t => types.has(t));
	});

	function startEditing(catId: number) {
		const cat = session.categories.find(c => c.id === catId);
		if (!cat) return;
		editingCatId = catId;
		editGroup = cat.family_type || '';
		editFamilyId = cat.family_id ?? 0;
	}

	function cancelEditing() {
		editingCatId = null;
		editGroup = '';
		editFamilyId = 0;
	}

	async function saveFamily(catId: number) {
		savingCatId = catId;
		try {
			await api.updateCategory(catId, { family_id: editFamilyId });
			editingCatId = null;
			onUpdate?.();
		} catch (e) {
			console.error('Failed to update category family:', e);
		}
		savingCatId = null;
	}

	async function handleCreateFamily() {
		if (!newFamilyName.trim()) return;
		try {
			const fam = await api.createFamily({
				name: newFamilyName.trim().toLowerCase().replace(/\s+/g, '_'),
				display_name: newFamilyName.trim(),
				family_type: newFamilyType,
			});
			families = [...families, fam];
			// Auto-select the new family in the editor
			editGroup = fam.family_type || 'other';
			editFamilyId = fam.id;
			newFamilyName = '';
			creatingFamily = false;
		} catch (e: unknown) {
			console.error('Failed to create family:', e);
		}
	}

	async function handleAddCategory() {
		const name = newCatName.trim();
		if (!name) return;
		addingCatLoading = true;
		addCatError = '';
		try {
			await api.addCategory(session.id, {
				name: name.toLowerCase().replace(/\s+/g, '_'),
				display_name: name,
			});
			newCatName = '';
			addingCategory = false;
			onUpdate?.();
		} catch (e: unknown) {
			addCatError = e instanceof Error ? e.message : 'Failed to add category';
		}
		addingCatLoading = false;
	}

	async function handleDeleteCategory(catId: number) {
		try {
			await api.deleteCategory(catId);
			onUpdate?.();
		} catch (e: unknown) {
			console.error('Failed to delete category:', e);
		}
	}

	function formatHours(minutes: number): string {
		const hours = Math.floor(minutes / 60);
		const mins = minutes % 60;
		if (hours === 0) return `${mins}m`;
		if (mins === 0) return `${hours}h`;
		return `${hours}h ${mins}m`;
	}

	function formatDecimalHours(minutes: number): string {
		return (minutes / 60).toFixed(1);
	}

	onMount(loadFamilies);
</script>

<div class="space-y-6">
	<!-- Session info card -->
	<div class="rounded-lg border border-border bg-card p-5">
		<div class="flex items-start justify-between">
			<div>
				<h2 class="text-xl font-semibold">{session.label}</h2>
				<p class="mt-1 text-sm text-muted-foreground">
					{#if session.start_date && session.end_date}
						{session.start_date} to {session.end_date}
					{:else}
						No date range
					{/if}
				</p>
			</div>
			{#if session.is_active}
				<span class="inline-flex items-center gap-1.5 rounded-full bg-green-500/10 px-2.5 py-1 text-xs font-medium text-green-700">
					<span class="h-1.5 w-1.5 rounded-full bg-green-500"></span>
					Active
				</span>
			{:else}
				<span class="inline-flex items-center rounded-full bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
					Archived
				</span>
			{/if}
		</div>

		<div class="mt-4 grid grid-cols-3 gap-4">
			<div class="rounded-lg bg-muted p-3">
				<div class="text-2xl font-bold">{formatDecimalHours(session.total_minutes)}</div>
				<div class="text-xs text-muted-foreground">Total hours</div>
			</div>
			<div class="rounded-lg bg-muted p-3">
				<div class="text-2xl font-bold">{session.days_logged}</div>
				<div class="text-xs text-muted-foreground">Days logged</div>
			</div>
			<div class="rounded-lg bg-muted p-3">
				<div class="text-2xl font-bold">{session.categories.length}</div>
				<div class="text-xs text-muted-foreground">Categories</div>
			</div>
		</div>
	</div>

	<!-- Categories table -->
	<div>
		<div class="mb-3 flex items-center justify-between">
			<h3 class="text-lg font-semibold">Categories</h3>
			{#if !addingCategory}
				<button
					onclick={() => { addingCategory = true; newCatName = ''; addCatError = ''; }}
					class="inline-flex items-center gap-1.5 rounded-lg border border-dashed border-border px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:border-primary hover:text-primary"
				>
					<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
					</svg>
					Add Category
				</button>
			{/if}
		</div>

		{#if addingCategory}
			<div class="mb-3 rounded-lg border border-primary/30 bg-primary/5 p-3">
				{#if addCatError}
					<div class="mb-2 text-sm text-red-600">{addCatError}</div>
				{/if}
				<div class="flex items-center gap-2">
					<input
						type="text"
						bind:value={newCatName}
						placeholder="Category name (e.g. Training, COGS 118C)"
						onkeydown={(e) => { if (e.key === 'Enter') handleAddCategory(); if (e.key === 'Escape') addingCategory = false; }}
						class="flex-1 rounded-md border border-border bg-background px-2.5 py-1.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
					/>
					<button
						onclick={handleAddCategory}
						disabled={!newCatName.trim() || addingCatLoading}
						class="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50"
					>
						{addingCatLoading ? 'Adding...' : 'Add'}
					</button>
					<button
						onclick={() => addingCategory = false}
						class="rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground"
					>
						Cancel
					</button>
				</div>
			</div>
		{/if}

		<div class="rounded-lg border border-border">
			<table class="w-full text-sm">
				<thead>
					<tr class="border-b border-border bg-muted/50">
						<th class="px-4 py-2.5 text-left font-medium text-muted-foreground">Category</th>
						<th class="px-4 py-2.5 text-left font-medium text-muted-foreground">Group</th>
						<th class="px-4 py-2.5 text-left font-medium text-muted-foreground">Family</th>
						<th class="px-4 py-2.5 text-right font-medium text-muted-foreground">Hours</th>
						<th class="w-10"></th>
					</tr>
				</thead>
				<tbody>
					{#each session.categories as cat}
						<tr class="border-b border-border last:border-0 hover:bg-muted/30">
							<td class="px-4 py-2.5">
								<span class="font-medium">{cat.display_name || cat.name}</span>
							</td>

							{#if editingCatId === cat.id}
								<!-- Editing mode: group + family selectors -->
								<td class="px-4 py-2.5">
									<select
										bind:value={editGroup}
										onchange={() => editFamilyId = 0}
										class="w-full rounded-md border border-border bg-background px-2 py-1 text-xs focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
									>
										<option value="">None</option>
										{#each availableGroups as g}
											<option value={g}>{GROUP_LABELS[g] || g}</option>
										{/each}
									</select>
								</td>
								<td class="px-4 py-2.5">
									<div class="flex items-center gap-1.5">
										<select
											bind:value={editFamilyId}
											disabled={!editGroup}
											class="w-full rounded-md border border-border bg-background px-2 py-1 text-xs focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-40"
										>
											<option value={0}>None</option>
											{#each familiesForGroup as fam}
												<option value={fam.id}>{fam.display_name || fam.name}</option>
											{/each}
										</select>
										<button
											onclick={() => { creatingFamily = true; newFamilyType = editGroup || 'other'; }}
											title="New family"
											class="shrink-0 rounded p-1 text-muted-foreground hover:text-primary transition-colors"
										>
											<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
												<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
											</svg>
										</button>
									</div>
								</td>
							{:else}
								<!-- Display mode: blue badges -->
								<td class="px-4 py-2.5">
									{#if cat.family_type}
										<span class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium {GROUP_COLORS[cat.family_type] || GROUP_COLORS['other']}">
											{GROUP_LABELS[cat.family_type] || cat.family_type}
										</span>
									{:else}
										<span class="text-muted-foreground">—</span>
									{/if}
								</td>
								<td class="px-4 py-2.5">
									{#if cat.family_display_name}
										<span class="inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
											{cat.family_display_name}
										</span>
									{:else}
										<span class="text-muted-foreground">—</span>
									{/if}
								</td>
							{/if}

							<td class="px-4 py-2.5 text-right tabular-nums">
								{formatHours(cat.total_minutes)}
							</td>
							<td class="px-4 py-2.5 text-right">
								{#if editingCatId === cat.id}
									<div class="flex items-center gap-1">
										<button
											onclick={() => saveFamily(cat.id)}
											disabled={savingCatId === cat.id}
											class="rounded p-1 text-green-600 hover:bg-green-500/10 transition-colors disabled:opacity-50"
											title="Save"
										>
											<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
												<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
											</svg>
										</button>
										<button
											onclick={cancelEditing}
											class="rounded p-1 text-muted-foreground hover:bg-muted transition-colors"
											title="Cancel"
										>
											<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
												<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
											</svg>
										</button>
									</div>
								{:else}
									<div class="flex items-center gap-1">
										<button
											onclick={() => startEditing(cat.id)}
											class="rounded p-1 text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
											title="Edit family"
										>
											<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
												<path stroke-linecap="round" stroke-linejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931z" />
											</svg>
										</button>
										{#if cat.total_minutes === 0}
											<button
												onclick={() => handleDeleteCategory(cat.id)}
												class="rounded p-1 text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors"
												title="Delete category"
											>
												<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
													<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
												</svg>
											</button>
										{/if}
									</div>
								{/if}
							</td>
						</tr>

						<!-- Inline new family form (appears below the editing row) -->
						{#if editingCatId === cat.id && creatingFamily}
							<tr class="border-b border-border bg-primary/5">
								<td colspan="5" class="px-4 py-3">
									<div class="flex items-end gap-2">
										<div class="flex-1">
											<label class="block text-xs font-medium text-muted-foreground mb-1">New Family Name</label>
											<input
												type="text"
												bind:value={newFamilyName}
												placeholder="e.g. Robotics Research"
												class="w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
											/>
										</div>
										<div>
											<label class="block text-xs font-medium text-muted-foreground mb-1">Group</label>
											<select
												bind:value={newFamilyType}
												class="rounded-md border border-border bg-background px-2.5 py-1.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
											>
												<option value="research">Research</option>
												<option value="course">Course</option>
												<option value="personal">Personal</option>
												<option value="other">Other</option>
											</select>
										</div>
										<button
											onclick={handleCreateFamily}
											disabled={!newFamilyName.trim()}
											class="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50"
										>
											Create
										</button>
										<button
											onclick={() => { creatingFamily = false; newFamilyName = ''; }}
											class="rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground"
										>
											Cancel
										</button>
									</div>
								</td>
							</tr>
						{/if}
					{/each}
				</tbody>
			</table>
		</div>
	</div>
</div>
