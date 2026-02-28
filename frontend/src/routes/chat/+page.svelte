<script lang="ts">
	import { onMount } from 'svelte';
	import ChatBubble from '$lib/components/chat/ChatBubble.svelte';
	import ApprovalCard from '$lib/components/chat/ApprovalCard.svelte';
	import ChatInput from '$lib/components/chat/ChatInput.svelte';
	import {
		messages,
		pendingApproval,
		isLoading,
		isStreaming,
		chatStatus,
		chatError,
		loadChatStatus,
		loadChatHistory,
		sendQuery,
		clearHistory
	} from '$lib/stores/chat';

	let messagesContainer: HTMLDivElement;

	onMount(() => {
		loadChatStatus();
		loadChatHistory();
	});

	// Auto-scroll on new messages
	$effect(() => {
		// Subscribe to messages changes
		const _ = $messages;
		if (messagesContainer) {
			requestAnimationFrame(() => {
				messagesContainer.scrollTop = messagesContainer.scrollHeight;
			});
		}
	});

	const suggestedQueries = [
		'Summarize my 2024 productivity',
		'How much time did I spend on training?',
		'Compare Fall 2024 and Winter 2025',
		'What are my top categories?'
	];

	function handleSend(message: string) {
		sendQuery(message);
	}

	function getModelName(modelId: string): string {
		const model = $chatStatus?.available_models.find((m) => m.id === modelId);
		return model?.name ?? modelId;
	}
</script>

<div class="flex h-full flex-col -m-6">
	<!-- Header -->
	<div class="flex items-center justify-between border-b border-border px-6 py-3">
		<div class="flex items-center gap-3">
			<h1 class="text-lg font-semibold">Chat</h1>
			{#if $chatStatus}
				<span class="rounded-full bg-muted px-2.5 py-0.5 text-xs text-muted-foreground">
					{getModelName($chatStatus.selected_model)}
				</span>
			{/if}
		</div>
		{#if $messages.length > 0}
			<button
				onclick={() => clearHistory()}
				class="rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted transition-colors"
			>
				Clear
			</button>
		{/if}
	</div>

	<!-- API key warning -->
	{#if $chatStatus && !$chatStatus.has_api_key}
		<div class="mx-6 mt-4 rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-900 dark:bg-amber-950/30">
			<div class="flex items-start gap-3">
				<svg class="mt-0.5 h-5 w-5 shrink-0 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
					<path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
				</svg>
				<div>
					<p class="text-sm font-medium text-amber-800 dark:text-amber-200">API key not configured</p>
					<p class="mt-1 text-xs text-amber-700 dark:text-amber-300">
						Add your Claude API key in <a href="/settings" class="underline font-medium">Settings</a> to start chatting.
					</p>
				</div>
			</div>
		</div>
	{/if}

	<!-- Messages area -->
	<div bind:this={messagesContainer} class="flex-1 overflow-y-auto px-6 py-4">
		{#if $messages.length === 0 && !$pendingApproval}
			<!-- Empty state with suggestions -->
			<div class="flex h-full flex-col items-center justify-center text-center">
				<div class="mb-2 flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10">
					<svg class="h-6 w-6 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
						<path stroke-linecap="round" stroke-linejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
					</svg>
				</div>
				<h2 class="text-lg font-semibold">Ask about your data</h2>
				<p class="mt-1 text-sm text-muted-foreground">
					Query your productivity history using natural language.
				</p>
				<div class="mt-6 flex flex-wrap justify-center gap-2">
					{#each suggestedQueries as query}
						<button
							onclick={() => handleSend(query)}
							disabled={!$chatStatus?.has_api_key}
							class="rounded-full border border-border px-4 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
						>
							{query}
						</button>
					{/each}
				</div>
			</div>
		{:else}
			<!-- Message list -->
			<div class="mx-auto max-w-3xl">
				{#each $messages as message}
					<ChatBubble {message} />
				{/each}

				{#if $pendingApproval}
					<ApprovalCard approval={$pendingApproval} />
				{/if}

				{#if $isLoading}
					<div class="flex justify-start mb-3">
						<div class="rounded-2xl rounded-bl-md bg-card border border-border px-4 py-3">
							<div class="flex gap-1">
								<span class="h-2 w-2 rounded-full bg-muted-foreground/40 animate-bounce" style="animation-delay: 0ms"></span>
								<span class="h-2 w-2 rounded-full bg-muted-foreground/40 animate-bounce" style="animation-delay: 150ms"></span>
								<span class="h-2 w-2 rounded-full bg-muted-foreground/40 animate-bounce" style="animation-delay: 300ms"></span>
							</div>
						</div>
					</div>
				{/if}

				{#if $isStreaming}
					<div class="flex justify-start mb-1">
						<span class="text-xs text-muted-foreground animate-pulse">Claude is typing...</span>
					</div>
				{/if}
			</div>
		{/if}
	</div>

	<!-- Error banner -->
	{#if $chatError}
		<div class="mx-6 mb-2 rounded-lg border border-destructive/20 bg-destructive/5 px-4 py-2">
			<div class="flex items-center justify-between">
				<p class="text-sm text-destructive">{$chatError}</p>
				<button
					onclick={() => chatError.set(null)}
					class="text-destructive/60 hover:text-destructive"
				>
					<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>
		</div>
	{/if}

	<!-- Input -->
	<ChatInput
		onSend={handleSend}
		disabled={!$chatStatus?.has_api_key || $isLoading || $isStreaming}
	/>
</div>
