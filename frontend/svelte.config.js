import adapter from '@sveltejs/adapter-static';

/**
 * Static SPA build. log(ger) is a client-rendered app with a single index.html
 * that handles all routes, served by FastAPI's StaticFiles mount in the packaged
 * Mac app. In dev, `pnpm dev` still uses Vite + the SvelteKit dev server.
 *
 * @type {import('@sveltejs/kit').Config}
 */
const config = {
	kit: {
		adapter: adapter({
			pages: 'build',
			assets: 'build',
			fallback: 'index.html', // SPA fallback — all routes serve the same index
			precompress: false,
			strict: true,
		}),
	},
};

export default config;
