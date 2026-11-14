<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type FamilyResponse, type CategoryGroupResponse } from '$lib/api/client';

	let { onChanged }: { onChanged?: () => void } = $props();

	let families = $state<FamilyResponse[]>([]);
	let groups = $state<CategoryGroupResponse[]>([]);
	let loading = $state(true);
	let editingId = $state<number | null>(null);
	let saving = $state(false);
	let creating = $state(false);
	let deleteConfirmId = $state<number | null>(null);

	// Edit form state
	let editName = $state('');
	let editDisplayName = $state('');
	let editGroupId = $state<number | null>(null);
	let editColor = $state('#6366f1');
	let editDescription = $state('');

	// New family form state
	let newName = $state('');
	let newDisplayName = $state('');
	let newGroupId = $state<number | null>(null);
	let newColor = $state('#6366f1');
	let newDescription = $state('');

	let error = $state('');

	// Filter box + Group sections. Families are shown under their Group
	// (Research, Courses, …) in group order, biggest first within a group;
	// families without a group collect in a trailing "Unassigned" section.
	let query = $state('');

	const sections = $derived.by(() => {
		const q = query.trim().toLowerCase();
		const visible = families.filter(
			(f) =>
				!q ||
				(f.display_name || '').toLowerCase().includes(q) ||
				f.name.toLowerCase().includes(q) ||
				(f.description || '').toLowerCase().includes(q)
		);
		const byMinutes = (a: FamilyResponse, b: FamilyResponse) => b.total_minutes - a.total_minutes;
		const out: { key: string; label: string; slug: string | null; families: FamilyResponse[]; total: number }[] = [];
		const ordered = [...groups].sort((a, b) => (a.position ?? 0) - (b.position ?? 0));
		const known = new Set(ordered.map((g) => g.id));
		for (const g of ordered) {
			const list = visible.filter((f) => f.group_id === g.id).sort(byMinutes);
			if (list.length) {
				out.push({
					key: `g${g.id}`,
					label: g.display_name || g.name,
					slug: g.name,
					families: list,
					total: list.reduce((s, f) => s + f.total_minutes, 0),
				});
			}
		}
		const loose = visible.filter((f) => f.group_id == null || !known.has(f.group_id)).sort(byMinutes);
		if (loose.length) {
			out.push({
				key: 'unassigned',
				label: 'Unassigned',
				slug: null,
				families: loose,
				total: loose.reduce((s, f) => s + f.total_minutes, 0),
			});
		}
		return out;
	});

	const maxFamilyMinutes = $derived(Math.max(1, ...families.map((f) => f.total_minutes)));

	// Group section badges: neutral pill + colored dot (readable in both themes;
	// matches SessionDetail's group badges).
	const GROUP_DOTS: Record<string, string> = {
		research: 'bg-blue-500',
		courses: 'bg-purple-500',
		personal: 'bg-amber-500',
		training: 'bg-red-500',
	};

	function groupDot(slug: string | null): string {
		return (slug && GROUP_DOTS[slug]) || 'bg-gray-400';
	}

	function formatHours(minutes: number): string {
		const hours = Math.floor(minutes / 60);
		const mins = minutes % 60;
		if (hours === 0) return `${mins}m`;
		if (mins === 0) return `${hours}h`;
		return `${hours}h ${mins}m`;
	}

	async function loadAll() {
		loading = true;
		try {
			[families, groups] = await Promise.all([api.getFamilies(), api.getGroups()]);
		} catch (e) {
			console.error('Failed to load families/groups:', e);
		}
		loading = false;
	}

	function startEditing(fam: FamilyResponse) {
		editingId = fam.id;
		editName = fam.name;
		editDisplayName = fam.display_name || '';
		editGroupId = fam.group_id ?? null;
		editColor = fam.color || '#6366f1';
		editDescription = fam.description || '';
		error = '';
	}

	function cancelEditing() {
		editingId = null;
		error = '';
	}

	async function saveEdit() {
		if (!editingId) return;
		saving = true;
		error = '';
		try {
			await api.updateFamily(editingId, {
				name: editName,
				display_name: editDisplayName || undefined,
				group_id: editGroupId ?? 0,  // 0 means detach
				color: editColor,
				description: editDescription || undefined,
			});
			editingId = null;
			await loadAll();
			onChanged?.();
		} catch (e: unknown) {
			error = e instanceof Error ? e.message : 'Failed to save';
		}
		saving = false;
	}

	function startCreating() {
		creating = true;
		newName = '';
		newDisplayName = '';
		// Default to the Research group if it exists
		newGroupId = groups.find((g) => g.name === 'research')?.id ?? groups[0]?.id ?? null;
		newColor = '#6366f1';
		newDescription = '';
		error = '';
	}

	function cancelCreating() {
		creating = false;
		error = '';
	}

	async function saveNew() {
		if (!newName.trim()) return;
		saving = true;
		error = '';
		try {
			await api.createFamily({
				name: newName.trim().toLowerCase().replace(/\s+/g, '_'),
				display_name: newDisplayName.trim() || newName.trim(),
				group_id: newGroupId,
				color: newColor,
			});
			creating = false;
			await loadAll();
			onChanged?.();
		} catch (e: unknown) {
			error = e instanceof Error ? e.message : 'Failed to create';
		}
		saving = false;
	}

	async function confirmDelete(familyId: number) {
		saving = true;
		error = '';
		try {
			await api.deleteFamily(familyId);
			deleteConfirmId = null;
			await loadAll();
			onChanged?.();
		} catch (e: unknown) {
			error = e instanceof Error ? e.message : 'Failed to delete';
		}
		saving = false;
	}

	onMount(loadAll);
</script>

<div class="space-y-5">
	<div class="flex flex-wrap items-center justify-between gap-3">
		<div>
			<h2 class="text-base font-semibold">Families</h2>
			<p class="text-xs text-muted-foreground">
				A family links the same project across sessions; its group sets where it rolls up.
			</p>
		</div>
		<div class="flex items-center gap-2">
			<div class="relative">
				<svg class="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-4.35-4.35M17 11a6 6 0 11-12 0 6 6 0 0112 0z" />
				</svg>
				<input
					type="search"
					bind:value={query}
					placeholder="Filter families"
					class="w-48 rounded-lg border border-border bg-background py-1.5 pl-8 pr-2.5 text-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
				/>
			</div>
			{#if !creating}
				<button
					onclick={startCreating}
					class="inline-flex items-center gap-1.5 rounded-lg border border-dashed border-border px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:border-primary hover:text-primary"
				>
					<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
					</svg>
					New Family
				</button>
			{/if}
		</div>
	</div>

	{#if error}
		<div class="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
			{error}
		</div>
	{/if}

	{#if creating}
		<div class="rounded-lg border border-primary/30 bg-primary/5 p-4">
			<h3 class="mb-3 text-sm font-medium">New Family</h3>
			<div class="grid grid-cols-2 gap-3">
				<div>
					<label class="block text-xs font-medium text-muted-foreground mb-1">Display Name</label>
					<input
						type="text"
						bind:value={newDisplayName}
						placeholder="e.g. Robotics Research"
						class="w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
					/>
				</div>
				<div>
					<label class="block text-xs font-medium text-muted-foreground mb-1">Internal Name</label>
					<input
						type="text"
						bind:value={newName}
						placeholder="e.g. robotics"
						class="w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
					/>
				</div>
				<div>
					<label class="block text-xs font-medium text-muted-foreground mb-1">Group</label>
					<select
						bind:value={newGroupId}
						class="w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
					>
						<option value={null}>— Unassigned —</option>
						{#each groups as g}
							<option value={g.id}>{g.display_name || g.name}</option>
						{/each}
					</select>
				</div>
				<div>
					<label class="block text-xs font-medium text-muted-foreground mb-1">Color</label>
					<div class="flex items-center gap-2">
						<input
							type="color"
							bind:value={newColor}
							class="h-8 w-8 cursor-pointer rounded border border-border"
						/>
						<input
							type="text"
							bind:value={newColor}
							class="flex-1 rounded-md border border-border bg-background px-2.5 py-1.5 text-sm font-mono focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
						/>
					</div>
				</div>
				<div class="col-span-2">
					<label class="block text-xs font-medium text-muted-foreground mb-1">Description</label>
					<input
						type="text"
						bind:value={newDescription}
						placeholder="Optional description"
						class="w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
					/>
				</div>
			</div>
			<div class="mt-3 flex items-center gap-2">
				<button
					onclick={saveNew}
					disabled={!newName.trim() || saving}
					class="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50"
				>
					{saving ? 'Creating...' : 'Create'}
				</button>
				<button
					onclick={cancelCreating}
					class="rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground"
				>
					Cancel
				</button>
			</div>
		</div>
	{/if}

	{#if loading}
		<div class="py-8 text-center text-sm text-muted-foreground">Loading...</div>
	{:else if families.length === 0}
		<div class="py-8 text-center text-sm text-muted-foreground">No families yet.</div>
	{:else}
		{#if sections.length === 0}
			<div class="rounded-xl border border-dashed border-border py-8 text-center text-sm text-muted-foreground">
				No families match “{query}”.
			</div>
		{/if}
		{#each sections as section (section.key)}
			<section>
				<div class="mb-2 flex items-baseline justify-between px-1">
					<div class="flex items-center gap-2">
						<span class="inline-flex items-center gap-1.5 rounded-full border border-border px-2 py-0.5 text-xs font-semibold text-foreground">
							<span class="h-1.5 w-1.5 rounded-full {groupDot(section.slug)}"></span>
							{section.label}
						</span>
						<span class="text-xs text-muted-foreground">
							{section.families.length} famil{section.families.length === 1 ? 'y' : 'ies'}
						</span>
					</div>
					<span class="text-xs tabular-nums text-muted-foreground">{formatHours(section.total)}</span>
				</div>
				<div class="overflow-hidden rounded-xl border border-border bg-card">
					<table class="w-full text-sm">
						<thead>
							<tr class="border-b border-border bg-muted/50">
								<th class="px-4 py-2 text-left text-xs font-medium text-muted-foreground">Family</th>
								<th class="w-28 px-4 py-2 text-right text-xs font-medium text-muted-foreground">Categories</th>
								<th class="w-40 px-4 py-2 text-right text-xs font-medium text-muted-foreground">Hours</th>
								<th class="w-20"></th>
							</tr>
						</thead>
						<tbody>
							{@render familyRows(section.families)}
						</tbody>
					</table>
				</div>
			</section>
		{/each}
	{/if}
</div>

{#snippet familyRows(list: FamilyResponse[])}
	{#each list as fam (fam.id)}
		{#if editingId === fam.id}
			<!-- Editing row -->
			<tr class="border-b border-border last:border-0 bg-primary/5">
				<td colspan="4" class="px-4 py-3">
					<div class="grid grid-cols-2 gap-3">
						<div>
							<label class="block text-xs font-medium text-muted-foreground mb-1">Display Name</label>
							<input
								type="text"
								bind:value={editDisplayName}
								class="w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
							/>
						</div>
						<div>
							<label class="block text-xs font-medium text-muted-foreground mb-1">Internal Name</label>
							<input
								type="text"
								bind:value={editName}
								class="w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
							/>
						</div>
						<div>
							<label class="block text-xs font-medium text-muted-foreground mb-1">Group</label>
							<select
								bind:value={editGroupId}
								class="w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
							>
								<option value={null}>— Unassigned —</option>
								{#each groups as g}
									<option value={g.id}>{g.display_name || g.name}</option>
								{/each}
							</select>
						</div>
						<div>
							<label class="block text-xs font-medium text-muted-foreground mb-1">Color</label>
							<div class="flex items-center gap-2">
								<input
									type="color"
									bind:value={editColor}
									class="h-8 w-8 cursor-pointer rounded border border-border"
								/>
								<input
									type="text"
									bind:value={editColor}
									class="flex-1 rounded-md border border-border bg-background px-2.5 py-1.5 text-sm font-mono focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
								/>
							</div>
						</div>
						<div class="col-span-2">
							<label class="block text-xs font-medium text-muted-foreground mb-1">Description</label>
							<input
								type="text"
								bind:value={editDescription}
								placeholder="Optional description"
								class="w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
							/>
						</div>
					</div>
					<div class="mt-3 flex items-center gap-2">
						<button
							onclick={saveEdit}
							disabled={saving}
							class="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50"
						>
							{saving ? 'Saving...' : 'Save'}
						</button>
						<button
							onclick={cancelEditing}
							class="rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground"
						>
							Cancel
						</button>
					</div>
				</td>
			</tr>
		{:else}
			<!-- Display row -->
			<tr class="border-b border-border last:border-0 hover:bg-muted/30">
				<td class="px-4 py-2.5">
					<div class="flex items-center gap-2.5">
						<span
							class="h-3 w-3 shrink-0 rounded-full"
							style="background-color: {fam.color || '#6366f1'}"
						></span>
						<div class="min-w-0">
							<span class="font-medium">{fam.display_name || fam.name}</span>
							{#if fam.display_name && fam.display_name !== fam.name}
								<span class="ml-1.5 text-xs text-muted-foreground">{fam.name}</span>
							{/if}
							{#if fam.description}
								<div class="truncate text-xs text-muted-foreground">{fam.description}</div>
							{/if}
						</div>
					</div>
				</td>
				<td class="px-4 py-2.5 text-right tabular-nums">
					{fam.category_count}
				</td>
				<td class="px-4 py-2.5 text-right">
					<div class="flex items-center justify-end gap-3">
						<div class="hidden h-1.5 w-16 overflow-hidden rounded-full bg-muted md:block" aria-hidden="true">
							<div
								class="h-full rounded-full"
								style="width: {(fam.total_minutes / maxFamilyMinutes) * 100}%; background-color: {fam.color || '#6366f1'}; opacity: 0.75"
							></div>
						</div>
						<span class="w-20 whitespace-nowrap tabular-nums">{formatHours(fam.total_minutes)}</span>
					</div>
				</td>
				<td class="px-4 py-2.5 text-right">
					{#if deleteConfirmId === fam.id}
						<div class="flex items-center gap-1">
							<button
								onclick={() => confirmDelete(fam.id)}
								disabled={saving}
								class="rounded p-1 text-red-600 hover:bg-red-500/10 transition-colors disabled:opacity-50"
								title="Confirm delete"
							>
								<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
								</svg>
							</button>
							<button
								onclick={() => deleteConfirmId = null}
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
								onclick={() => startEditing(fam)}
								class="rounded p-1 text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
								title="Edit"
							>
								<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
									<path stroke-linecap="round" stroke-linejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931z" />
								</svg>
							</button>
							<button
								onclick={() => deleteConfirmId = fam.id}
								class="rounded p-1 text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors"
								title="Delete"
							>
								<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
									<path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
								</svg>
							</button>
						</div>
					{/if}
				</td>
			</tr>
			<!-- Delete confirmation banner -->
			{#if deleteConfirmId === fam.id && fam.category_count > 0}
				<tr class="border-b border-border last:border-0">
					<td colspan="4" class="px-4 py-2 bg-red-50 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
						{fam.category_count} categor{fam.category_count === 1 ? 'y' : 'ies'} will be unlinked from this family. Are you sure?
					</td>
				</tr>
			{/if}
		{/if}
	{/each}
{/snippet}
