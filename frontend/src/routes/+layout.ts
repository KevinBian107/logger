// SPA: render entirely on the client. adapter-static + fallback: 'index.html'
// makes the build a single HTML file with client-side routing. The packaged
// FastAPI app serves it from StaticFiles(html=True) and lets the browser
// handle all in-app navigation.
export const prerender = false;
export const ssr = false;
