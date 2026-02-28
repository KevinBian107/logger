<script lang="ts">
	import { onMount } from 'svelte';
	import {
		api,
		type GroupListResponse,
		type GroupDetailResponse,
		type GroupFamilyItem,
	} from '$lib/api/client';
	import FamilySelector from '$lib/components/projects/FamilySelector.svelte';
	import VerticalTimeline from '$lib/components/projects/VerticalTimeline.svelte';
	import GitHubPanel from '$lib/components/projects/GitHubPanel.svelte';

	let groupList = $state<GroupListResponse | null>(null);
	let groupDetail = $state<GroupDetailResponse | null>(null);
	let loading = $state(true);
	let detailLoading = $state(false);
	let error = $state<string | null>(null);
	let hasApiKey = $state(false);
	let selectedGroupType = $state<string | null>(null);

	// Track which family sections are collapsed
	let collapsedFamilies = $state<Set<number>>(new Set());

	async function loadGroups() {
		loading = true;
		error = null;
		try {
			const [data, status] = await Promise.all([
				api.getProjectGroups(),
				api.getChatStatus()
			]);
			groupList = data;
			hasApiKey = status.has_api_key;

			// Auto-select first group (typically "research" as highest hours)
			if (data.groups.length > 0 && !selectedGroupType) {
				selectGroup(data.groups[0].group_type);
			}
		} catch (e: unknown) {
			error = e instanceof Error ? e.message : 'Failed to load project groups';
		} finally {
			loading = false;
		}
	}

	async function selectGroup(groupType: string) {
		selectedGroupType = groupType;
		detailLoading = true;
		collapsedFamilies = new Set();
		try {
			groupDetail = await api.getGroupDetail(groupType);
		} catch {
			groupDetail = null;
		} finally {
			detailLoading = false;
		}
	}

	function toggleFamily(familyId: number) {
		const next = new Set(collapsedFamilies);
		if (next.has(familyId)) {
			next.delete(familyId);
		} else {
			next.add(familyId);
		}
		collapsedFamilies = next;
	}

	async function handleGenerate(familyId: number, sessionId: number) {
		const result = await api.generateEnrichedDescription(familyId, sessionId, true);
		// Update local data
		if (groupDetail) {
			const family = groupDetail.families.find(f => f.family_id === familyId);
			if (family) {
				const session = family.sessions.find(s => s.session_id === sessionId);
				if (session) {
					session.ai_description = result.description;
					groupDetail = { ...groupDetail };
				}
			}
		}
	}

	async function handleRepoChanged() {
		if (selectedGroupType) {
			groupDetail = await api.getGroupDetail(selectedGroupType);
			groupList = await api.getProjectGroups();
		}
	}

	function formatHours(minutes: number): string {
		const h = Math.floor(minutes / 60);
		const m = minutes % 60;
		if (h === 0) return `${m}m`;
		if (m === 0) return `${h}h`;
		return `${h}h ${m}m`;
	}

	onMount(() => {
		loadGroups();
	});
</script>

<div class="flex h-full gap-6">
	<!-- Left sidebar: Group selector -->
	<div class="w-56 shrink-0">
		<div class="mb-4">
			<h1 class="text-xl font-bold">Projects</h1>
			<p class="text-xs text-muted-foreground mt-0.5">Evolution across sessions</p>
		</div>

		{#if loading}
			<div class="flex items-center justify-center py-8 text-sm text-muted-foreground">
				Loading...
			</div>
		{:else if error}
			<div class="rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-xs text-destructive">
				{error}
			</div>
		{:else if groupList && groupList.groups.length === 0}
			<div class="rounded-lg border border-border bg-card p-4 text-center">
				<p class="text-sm font-medium">No data yet</p>
				<p class="mt-0.5 text-xs text-muted-foreground">
					Import session data to see projects here.
				</p>
			</div>
		{:else if groupList}
			<FamilySelector
				groups={groupList.groups}
				{selectedGroupType}
				onSelect={selectGroup}
			/>
		{/if}
	</div>

	<!-- Right panel: All families in the group -->
	<div class="flex-1 min-w-0 overflow-y-auto">
		{#if detailLoading}
			<div class="flex items-center justify-center py-16 text-sm text-muted-foreground">
				<svg class="mr-2 h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
					<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
					<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
				</svg>
				Loading...
			</div>
		{:else if groupDetail}
			<!-- Group header -->
			<div class="mb-6">
				<h2 class="text-xl font-bold">{groupDetail.label}</h2>
				<div class="mt-1 flex items-center gap-4 text-sm text-muted-foreground">
					<span>{groupDetail.families.length} project{groupDetail.families.length !== 1 ? 's' : ''}</span>
					<span>{formatHours(groupDetail.families.reduce((sum, f) => sum + f.total_minutes, 0))} total</span>
				</div>
			</div>

			{#if groupDetail.families.length === 0}
				<div class="rounded-lg border border-border bg-card p-8 text-center">
					<p class="text-sm text-muted-foreground">No families in this group.</p>
				</div>
			{:else}
				<!-- Family sections -->
				<div class="space-y-6">
					{#each groupDetail.families as family (family.family_id)}
						<div class="rounded-xl border border-border bg-card overflow-hidden">
							<!-- Family header (clickable to collapse) -->
							<button
								onclick={() => toggleFamily(family.family_id)}
								class="w-full flex items-center gap-3 px-5 py-4 text-left hover:bg-muted/30 transition-colors"
							>
								<div
									class="h-3.5 w-3.5 shrink-0 rounded-full"
									style="background-color: {family.color || '#6366f1'}"
								></div>
								<div class="min-w-0 flex-1">
									<h3 class="text-base font-semibold truncate">
										{family.display_name || family.family_name}
									</h3>
									<div class="flex items-center gap-3 text-xs text-muted-foreground mt-0.5">
										<span>{formatHours(family.total_minutes)}</span>
										<span>{family.sessions.length} session{family.sessions.length !== 1 ? 's' : ''}</span>
										{#if family.linked_repo_count > 0}
											<span class="flex items-center gap-1">
												<svg class="h-3 w-3" viewBox="0 0 24 24" fill="currentColor">
													<path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
												</svg>
												{family.linked_repo_count} repo{family.linked_repo_count !== 1 ? 's' : ''}
											</span>
										{/if}
									</div>
								</div>
								<!-- Expand/collapse chevron -->
								<svg
									class="h-4 w-4 shrink-0 text-muted-foreground transition-transform {collapsedFamilies.has(family.family_id) ? '-rotate-90' : 'rotate-0'}"
									fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"
								>
									<path stroke-linecap="round" stroke-linejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
								</svg>
							</button>

							<!-- Collapsible body -->
							{#if !collapsedFamilies.has(family.family_id)}
								<div class="border-t border-border px-5 py-4 space-y-5">
									<!-- GitHub panel (only for research) -->
									{#if selectedGroupType === 'research'}
										<GitHubPanel
											githubRepos={family.github_repos}
											linkedRepoCount={family.linked_repo_count}
											githubUsername={groupDetail.github_username}
											familyId={family.family_id}
											onChanged={handleRepoChanged}
										/>
									{/if}

									<!-- Vertical timeline -->
									<VerticalTimeline
										sessions={family.sessions}
										familyColor={family.color}
										{hasApiKey}
										onGenerate={(sessionId) => handleGenerate(family.family_id, sessionId)}
									/>
								</div>
							{/if}
						</div>
					{/each}
				</div>
			{/if}
		{:else if !loading && selectedGroupType === null}
			<div class="flex items-center justify-center py-16 text-sm text-muted-foreground">
				Select a group to view projects
			</div>
		{/if}
	</div>
</div>
