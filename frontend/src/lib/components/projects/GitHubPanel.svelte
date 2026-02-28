<script lang="ts">
	import { api, type GitHubRepoInfo } from '$lib/api/client';

	let {
		githubRepos,
		linkedRepoCount,
		githubUsername,
		familyId,
		onChanged
	}: {
		githubRepos: GitHubRepoInfo[];
		linkedRepoCount: number;
		githubUsername: string | null;
		familyId: number;
		onChanged: () => void;
	} = $props();

	let searching = $state(false);
	let searchResults = $state<GitHubRepoInfo[] | null>(null);
	let searchError = $state<string | null>(null);
	let showSearch = $state(false);
	let linking = $state(false);

	// Track repos being unlinked
	let unlinkingRepos = $state<Set<string>>(new Set());

	// Filter out already-linked repos from search results
	let linkedNames = $derived(new Set(githubRepos.map(r => r.full_name)));
	let filteredResults = $derived(
		searchResults?.filter(r => !linkedNames.has(r.full_name)) ?? null
	);

	async function handleSearch() {
		searching = true;
		searchError = null;
		try {
			const result = await api.searchGithubRepos();
			searchResults = result.repos;
		} catch (e) {
			searchError = e instanceof Error ? e.message : 'Failed to search';
		} finally {
			searching = false;
		}
	}

	async function handleLink(repoFullName: string) {
		linking = true;
		try {
			await api.linkGithubRepo(familyId, repoFullName);
			onChanged();
		} catch {
			// ignore
		} finally {
			linking = false;
		}
	}

	async function handleUnlink(repoFullName: string) {
		unlinkingRepos = new Set([...unlinkingRepos, repoFullName]);
		try {
			await api.unlinkGithubRepo(familyId, repoFullName);
			onChanged();
		} catch {
			// ignore
		} finally {
			const next = new Set(unlinkingRepos);
			next.delete(repoFullName);
			unlinkingRepos = next;
		}
	}
</script>

<div class="rounded-lg border border-border bg-card p-4">
	<div class="flex items-center justify-between mb-3">
		<div class="flex items-center gap-2">
			<svg class="h-4 w-4 text-muted-foreground" viewBox="0 0 24 24" fill="currentColor">
				<path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
			</svg>
			<h3 class="text-sm font-medium">GitHub Repos</h3>
			{#if linkedRepoCount > 0}
				<span class="rounded-full bg-green-100 px-1.5 py-0.5 text-[10px] font-medium text-green-700 dark:bg-green-900/30 dark:text-green-400">
					{linkedRepoCount}
				</span>
			{/if}
		</div>
		{#if githubUsername}
			<button
				onclick={() => { showSearch = !showSearch; if (!searchResults) handleSearch(); }}
				class="text-[11px] text-primary hover:underline"
			>
				{showSearch ? 'Close' : '+ Add repo'}
			</button>
		{/if}
	</div>

	{#if !githubUsername}
		<p class="text-xs text-muted-foreground">
			Set GitHub username and token in <a href="/settings" class="underline font-medium text-foreground">Settings</a> to link repositories.
		</p>
	{:else if githubRepos.length === 0 && !showSearch}
		<p class="text-xs text-muted-foreground">No repositories linked yet. Click "+ Add repo" above.</p>
	{:else}
		<!-- Linked repos list -->
		<div class="space-y-2">
			{#each githubRepos as repo}
				<div class="rounded-md border border-border bg-muted/20 px-3 py-2">
					<div class="flex items-center justify-between">
						<a
							href={repo.html_url || '#'}
							target="_blank"
							rel="noopener noreferrer"
							class="text-xs font-medium text-primary hover:underline truncate"
						>
							{repo.full_name}
						</a>
						<button
							onclick={() => handleUnlink(repo.full_name)}
							disabled={unlinkingRepos.has(repo.full_name)}
							class="shrink-0 ml-2 text-[10px] text-destructive hover:underline disabled:opacity-50"
						>
							{unlinkingRepos.has(repo.full_name) ? '...' : 'Remove'}
						</button>
					</div>
					<div class="flex items-center gap-3 mt-0.5 text-[10px] text-muted-foreground">
						{#if repo.language}
							<span>{repo.language}</span>
						{/if}
						{#if repo.description}
							<span class="truncate">{repo.description}</span>
						{/if}
					</div>
				</div>
			{/each}
		</div>
	{/if}

	<!-- Search results dropdown -->
	{#if showSearch}
		<div class="mt-3 border-t border-border pt-3">
			{#if searching}
				<div class="flex items-center gap-2 text-xs text-muted-foreground py-2">
					<svg class="h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24">
						<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
						<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
					</svg>
					Loading repos from @{githubUsername}...
				</div>
			{:else if searchError}
				<p class="text-xs text-destructive">{searchError}</p>
			{:else if filteredResults}
				<div class="max-h-52 overflow-y-auto space-y-0.5">
					{#each filteredResults as repo}
						<button
							onclick={() => handleLink(repo.full_name)}
							disabled={linking}
							class="w-full rounded-md px-2 py-1.5 text-left hover:bg-muted transition-colors disabled:opacity-50"
						>
							<div class="flex items-center gap-2">
								<span class="text-xs font-medium">{repo.name}</span>
								{#if repo.description?.startsWith('[PRIVATE]')}
									<span class="rounded bg-amber-100 px-1 py-0.5 text-[9px] font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
										Private
									</span>
								{/if}
							</div>
							{#if repo.description}
								<div class="text-[10px] text-muted-foreground truncate">
									{repo.description.replace('[PRIVATE] ', '')}
								</div>
							{/if}
						</button>
					{/each}
					{#if filteredResults.length === 0}
						<p class="text-xs text-muted-foreground py-2">
							{searchResults && searchResults.length > 0
								? 'All repos are already linked.'
								: 'No repositories found. Check your token in Settings.'}
						</p>
					{/if}
				</div>
			{/if}
		</div>
	{/if}
</div>
