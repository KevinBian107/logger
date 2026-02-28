<script lang="ts">
	import type { ChatMessageResponse } from '$lib/api/client';
	import { renderMarkdown } from '$lib/utils/markdown';

	let { message }: { message: ChatMessageResponse } = $props();

	const isUser = $derived(message.role === 'user');
	const isSystem = $derived(message.role === 'system');
	const rendered = $derived(
		isUser || isSystem ? message.content : renderMarkdown(message.content)
	);
</script>

{#if isSystem}
	<div class="flex justify-center py-1">
		<span class="text-xs text-muted-foreground italic">{message.content}</span>
	</div>
{:else}
	<div class="flex {isUser ? 'justify-end' : 'justify-start'} mb-3">
		<div
			class="max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed
				{isUser
					? 'bg-primary text-primary-foreground rounded-br-md'
					: 'bg-card border border-border text-card-foreground rounded-bl-md'}"
		>
			{#if isUser}
				{message.content}
			{:else}
				<div class="chat-markdown">
					{@html rendered}
				</div>
			{/if}
		</div>
	</div>
{/if}

<style>
	.chat-markdown :global(h1) {
		font-size: 1.25rem;
		font-weight: 700;
		margin: 0.75rem 0 0.25rem;
	}
	.chat-markdown :global(h2) {
		font-size: 1.1rem;
		font-weight: 600;
		margin: 0.625rem 0 0.25rem;
	}
	.chat-markdown :global(h3) {
		font-size: 1rem;
		font-weight: 600;
		margin: 0.5rem 0 0.25rem;
	}
	.chat-markdown :global(strong) {
		font-weight: 600;
	}
	.chat-markdown :global(em) {
		font-style: italic;
	}
	.chat-markdown :global(.md-list) {
		padding-left: 1.25rem;
		margin: 0.25rem 0;
		list-style: disc;
	}
	.chat-markdown :global(.md-list li) {
		margin: 0.125rem 0;
	}
	.chat-markdown :global(.md-inline-code) {
		background: var(--color-muted);
		padding: 0.125rem 0.375rem;
		border-radius: 0.25rem;
		font-family: monospace;
		font-size: 0.85em;
	}
	.chat-markdown :global(.md-code-block) {
		background: var(--color-muted);
		padding: 0.75rem;
		border-radius: 0.375rem;
		overflow-x: auto;
		margin: 0.5rem 0;
		font-size: 0.85em;
	}
	.chat-markdown :global(.md-code-block code) {
		font-family: monospace;
	}
	.chat-markdown :global(p) {
		margin: 0.25rem 0;
	}
</style>
