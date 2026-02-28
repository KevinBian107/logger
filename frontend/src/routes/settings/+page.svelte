<script lang="ts">
	import { onMount } from 'svelte';
	import { theme } from '$lib/stores/theme';
	import { api, type DBInfoResponse, type ChatStatusResponse, type SettingResponse } from '$lib/api/client';

	let dbInfo = $state<DBInfoResponse | null>(null);
	let apiKey = $state('');
	let chatStatusData = $state<ChatStatusResponse | null>(null);
	let saveMessage = $state<string | null>(null);
	let saving = $state(false);

	// GitHub
	let githubUsername = $state('');
	let savedGithubUsername = $state<string | null>(null);
	let githubToken = $state('');
	let hasGithubToken = $state(false);
	let githubPublicOnly = $state(false);
	let githubSaving = $state(false);
	let githubMessage = $state<string | null>(null);

	onMount(async () => {
		try {
			const [db, status, settings] = await Promise.all([
				api.getDBInfo(),
				api.getChatStatus(),
				api.getSettings()
			]);
			dbInfo = db;
			chatStatusData = status;
			const ghSetting = settings.find((s: SettingResponse) => s.key === 'github_username');
			if (ghSetting) {
				savedGithubUsername = ghSetting.value;
				githubUsername = ghSetting.value;
			}
			const ghToken = settings.find((s: SettingResponse) => s.key === 'github_token');
			if (ghToken && ghToken.value) {
				hasGithubToken = true;
			}
			const ghPublic = settings.find((s: SettingResponse) => s.key === 'github_public_only');
			if (ghPublic && ghPublic.value === 'true') {
				githubPublicOnly = true;
			}
		} catch {
			// API not available
		}
	});

	function formatBytes(bytes: number): string {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}

	function setTheme(value: string) {
		theme.set(value as 'light' | 'dark' | 'system');
	}

	async function handleSaveKey() {
		if (!apiKey.trim()) return;
		saving = true;
		saveMessage = null;
		try {
			await api.saveApiKey(apiKey);
			chatStatusData = await api.getChatStatus();
			apiKey = '';
			saveMessage = 'API key saved successfully';
			setTimeout(() => (saveMessage = null), 3000);
		} catch (e) {
			saveMessage = e instanceof Error ? e.message : 'Failed to save';
		} finally {
			saving = false;
		}
	}

	async function handleDeleteKey() {
		try {
			await api.deleteApiKey();
			chatStatusData = await api.getChatStatus();
			saveMessage = 'API key removed';
			setTimeout(() => (saveMessage = null), 3000);
		} catch (e) {
			saveMessage = e instanceof Error ? e.message : 'Failed to remove';
		}
	}

	async function handleSaveGithub() {
		if (!githubUsername.trim()) return;
		githubSaving = true;
		githubMessage = null;
		try {
			await api.updateSetting('github_username', githubUsername.trim());
			savedGithubUsername = githubUsername.trim();
			githubMessage = 'GitHub username saved';
			setTimeout(() => (githubMessage = null), 3000);
		} catch (e) {
			githubMessage = e instanceof Error ? e.message : 'Failed to save';
		} finally {
			githubSaving = false;
		}
	}

	async function handleTogglePublicOnly() {
		githubPublicOnly = !githubPublicOnly;
		try {
			await api.updateSetting('github_public_only', githubPublicOnly ? 'true' : 'false');
			await api.clearGithubCache().catch(() => {});
			githubMessage = githubPublicOnly ? 'Switched to public repos only' : 'Token enabled — private repos accessible';
			setTimeout(() => (githubMessage = null), 3000);
		} catch {
			githubPublicOnly = !githubPublicOnly; // revert
		}
	}

	async function handleSaveToken() {
		if (!githubToken.trim()) return;
		githubSaving = true;
		githubMessage = null;
		try {
			await api.updateSetting('github_token', githubToken.trim());
			// Clear repo cache so next search uses the new token
			await api.clearGithubCache().catch(() => {});
			hasGithubToken = true;
			githubToken = '';
			githubMessage = 'Token saved — private repos now accessible';
			setTimeout(() => (githubMessage = null), 3000);
		} catch (e) {
			githubMessage = e instanceof Error ? e.message : 'Failed to save';
		} finally {
			githubSaving = false;
		}
	}

	async function handleRemoveToken() {
		githubSaving = true;
		githubMessage = null;
		try {
			await api.updateSetting('github_token', '');
			hasGithubToken = false;
			githubMessage = 'Token removed';
			setTimeout(() => (githubMessage = null), 3000);
		} catch (e) {
			githubMessage = e instanceof Error ? e.message : 'Failed to remove';
		} finally {
			githubSaving = false;
		}
	}

	async function handleRemoveGithub() {
		githubSaving = true;
		githubMessage = null;
		try {
			await api.updateSetting('github_username', '');
			savedGithubUsername = null;
			githubUsername = '';
			githubMessage = 'GitHub username removed';
			setTimeout(() => (githubMessage = null), 3000);
		} catch (e) {
			githubMessage = e instanceof Error ? e.message : 'Failed to remove';
		} finally {
			githubSaving = false;
		}
	}

	async function handleModelChange(modelId: string) {
		try {
			await api.setChatModel(modelId);
			if (chatStatusData) {
				chatStatusData = { ...chatStatusData, selected_model: modelId };
			}
		} catch {
			// ignore
		}
	}
</script>

<div class="mx-auto max-w-2xl space-y-8">
	<h1 class="text-2xl font-bold">Settings</h1>

	<!-- Appearance -->
	<section class="space-y-4">
		<h2 class="text-lg font-semibold">Appearance</h2>
		<div class="rounded-lg border border-border bg-card p-5">
			<span class="text-sm font-medium">Theme</span>
			<div class="mt-2 flex gap-2">
				{#each ['light', 'dark', 'system'] as opt}
					<button
						onclick={() => setTheme(opt)}
						class="rounded-lg border px-4 py-2 text-sm font-medium transition-colors
							{$theme === opt
								? 'border-primary bg-primary/10 text-primary'
								: 'border-border text-muted-foreground hover:bg-muted'}"
					>
						{opt.charAt(0).toUpperCase() + opt.slice(1)}
					</button>
				{/each}
			</div>
		</div>
	</section>

	<!-- AI Configuration -->
	<section class="space-y-4">
		<h2 class="text-lg font-semibold">AI Configuration</h2>
		<div class="rounded-lg border border-border bg-card p-5 space-y-4">
			<!-- Status badge -->
			<div class="flex items-center justify-between">
				<span class="text-sm font-medium">Claude API Key</span>
				{#if chatStatusData}
					{#if chatStatusData.has_api_key}
						<span class="flex items-center gap-1.5 rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/30 dark:text-green-400">
							<span class="h-1.5 w-1.5 rounded-full bg-green-500"></span>
							Connected
						</span>
					{:else}
						<span class="flex items-center gap-1.5 rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-medium text-red-700 dark:bg-red-900/30 dark:text-red-400">
							<span class="h-1.5 w-1.5 rounded-full bg-red-500"></span>
							Not configured
						</span>
					{/if}
				{/if}
			</div>

			<p class="text-xs text-muted-foreground">Required for Chat and Project descriptions</p>

			<div class="flex gap-2">
				<input
					id="api-key"
					type="password"
					bind:value={apiKey}
					placeholder="sk-ant-..."
					class="flex-1 rounded-lg border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
				/>
				<button
					onclick={handleSaveKey}
					disabled={!apiKey.trim() || saving}
					class="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
				>
					{saving ? 'Saving...' : 'Save'}
				</button>
			</div>

			{#if chatStatusData?.has_api_key}
				<button
					onclick={handleDeleteKey}
					class="text-xs text-destructive hover:underline"
				>
					Remove API key
				</button>
			{/if}

			{#if saveMessage}
				<p class="text-xs {saveMessage.includes('success') || saveMessage.includes('removed') ? 'text-green-600 dark:text-green-400' : 'text-destructive'}">
					{saveMessage}
				</p>
			{/if}

			<!-- Model selector -->
			{#if chatStatusData}
				<div class="border-t border-border pt-4">
					<label for="model-select" class="text-sm font-medium">Chat Model</label>
					<p class="text-xs text-muted-foreground mt-0.5 mb-2">Select which Claude model to use for chat</p>
					<select
						id="model-select"
						onchange={(e) => handleModelChange((e.target as HTMLSelectElement).value)}
						class="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
					>
						{#each chatStatusData.available_models as model}
							<option value={model.id} selected={model.id === chatStatusData.selected_model}>
								{model.name}
							</option>
						{/each}
					</select>
				</div>
			{/if}
		</div>
	</section>

	<!-- GitHub Integration -->
	<section class="space-y-4">
		<h2 class="text-lg font-semibold">GitHub Integration</h2>
		<div class="rounded-lg border border-border bg-card p-5 space-y-4">
			<div class="flex items-center justify-between">
				<span class="text-sm font-medium">GitHub Username</span>
				{#if savedGithubUsername}
					<span class="flex items-center gap-1.5 rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-medium text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
						@{savedGithubUsername}
					</span>
				{:else}
					<span class="flex items-center gap-1.5 rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs font-medium text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
						Not set
					</span>
				{/if}
			</div>

			<p class="text-xs text-muted-foreground">
				Used to enrich research project descriptions with GitHub repo data
			</p>

			<div class="flex gap-2">
				<input
					type="text"
					bind:value={githubUsername}
					placeholder="your-username"
					class="flex-1 rounded-lg border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
				/>
				<button
					onclick={handleSaveGithub}
					disabled={!githubUsername.trim() || githubSaving}
					class="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
				>
					{githubSaving ? 'Saving...' : 'Save'}
				</button>
			</div>

			{#if savedGithubUsername}
				<button
					onclick={handleRemoveGithub}
					class="text-xs text-destructive hover:underline"
				>
					Remove username
				</button>
			{/if}

			<!-- Repo access mode -->
			<div class="border-t border-border pt-4">
				<div class="flex items-center justify-between">
					<span class="text-sm font-medium">Repo Access</span>
					<div class="flex items-center gap-2">
						<button
							onclick={handleTogglePublicOnly}
							class="relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors {githubPublicOnly ? 'bg-muted-foreground/30' : 'bg-primary'}"
						>
							<span
								class="pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow transition-transform {githubPublicOnly ? 'translate-x-0' : 'translate-x-4'}"
							></span>
						</button>
						<span class="text-xs text-muted-foreground">
							{githubPublicOnly ? 'Public repos only' : 'Include private repos'}
						</span>
					</div>
				</div>
				<p class="text-xs text-muted-foreground mt-1">
					{githubPublicOnly
						? 'Only public repos are shown. No token needed.'
						: 'Uses your token to access private repos and repos you contribute to.'}
				</p>
			</div>

			<!-- Personal Access Token (hidden in public-only mode) -->
			{#if !githubPublicOnly}
				<div class="border-t border-border pt-4">
					<div class="flex items-center justify-between">
						<span class="text-sm font-medium">Personal Access Token</span>
						{#if hasGithubToken}
							<span class="flex items-center gap-1.5 rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/30 dark:text-green-400">
								<span class="h-1.5 w-1.5 rounded-full bg-green-500"></span>
								Configured
							</span>
						{:else}
							<span class="flex items-center gap-1.5 rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
								Needed for private repos
							</span>
						{/if}
					</div>
					<p class="text-xs text-muted-foreground mt-1 mb-2">
						Add a <a href="https://github.com/settings/tokens" target="_blank" rel="noopener noreferrer" class="underline font-medium text-foreground">personal access token</a> to access private repos and repos you contribute to. Needs <code class="text-[10px] bg-muted px-1 py-0.5 rounded">repo</code> scope.
					</p>
					<div class="flex gap-2">
						<input
							type="password"
							bind:value={githubToken}
							placeholder="ghp_..."
							class="flex-1 rounded-lg border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
						/>
						<button
							onclick={handleSaveToken}
							disabled={!githubToken.trim() || githubSaving}
							class="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
						>
							{githubSaving ? 'Saving...' : 'Save'}
						</button>
					</div>
					{#if hasGithubToken}
						<button
							onclick={handleRemoveToken}
							class="mt-2 text-xs text-destructive hover:underline"
						>
							Remove token
						</button>
					{/if}
				</div>
			{/if}

			{#if githubMessage}
				<p class="text-xs {githubMessage.includes('saved') || githubMessage.includes('removed') ? 'text-green-600 dark:text-green-400' : 'text-destructive'}">
					{githubMessage}
				</p>
			{/if}
		</div>
	</section>

	<!-- Database Info -->
	<section class="space-y-4">
		<h2 class="text-lg font-semibold">Database</h2>
		<div class="rounded-lg border border-border bg-card p-5">
			{#if dbInfo}
				<div class="space-y-3 text-sm">
					<div class="flex justify-between">
						<span class="text-muted-foreground">Path</span>
						<span class="font-mono text-xs">{dbInfo.db_path}</span>
					</div>
					<div class="flex justify-between">
						<span class="text-muted-foreground">Size</span>
						<span>{formatBytes(dbInfo.db_size_bytes)}</span>
					</div>
					<div class="flex justify-between">
						<span class="text-muted-foreground">Sessions</span>
						<span>{dbInfo.session_count}</span>
					</div>
					<div class="flex justify-between">
						<span class="text-muted-foreground">Observations</span>
						<span>{dbInfo.observation_count.toLocaleString()}</span>
					</div>
					<div class="flex justify-between">
						<span class="text-muted-foreground">Text entries</span>
						<span>{dbInfo.text_entry_count.toLocaleString()}</span>
					</div>
				</div>
			{:else}
				<p class="text-sm text-muted-foreground">Could not connect to backend</p>
			{/if}
		</div>
	</section>
</div>
