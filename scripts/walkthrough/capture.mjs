// Drives the REAL running app (backend + frontend dev servers, pointed at
// the throwaway demo DB seeded by seed_demo_data.py) through the actual
// Plan -> Track -> Recorder -> Analyze -> Ask loop, saving screenshots and
// two short silent video clips into website/assets/walkthrough/.
//
// Usage: node scripts/walkthrough/capture.mjs
// Expects the backend on :8000 and frontend dev server on :5173 already
// running against the seeded demo DB (see run.sh, which wires this up).
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';

const BASE = 'http://localhost:5173';
const OUT = path.resolve('website/assets/walkthrough');
fs.mkdirSync(OUT, { recursive: true });

const VIEWPORT = { width: 1440, height: 900 };
// Explicit numeric prefixes (not auto-incrementing) so trimming a shot that a
// video clip already covers doesn't silently renumber every file after it.
async function shot(page, num, name) {
	await page.screenshot({ path: path.join(OUT, `${String(num).padStart(2, '0')}-${name}.png`) });
	console.log('shot:', name);
}

async function recordClip(browser, name, viewport, run) {
	const tmpDir = path.join(OUT, `_tmp-${name}`);
	fs.rmSync(tmpDir, { recursive: true, force: true });
	fs.mkdirSync(tmpDir, { recursive: true });
	const context = await browser.newContext({ viewport, recordVideo: { dir: tmpDir, size: viewport } });
	const page = await context.newPage();
	await run(page);
	await context.close(); // flushes the .webm to tmpDir
	const file = fs.readdirSync(tmpDir).find((f) => f.endsWith('.webm'));
	const dest = path.join(OUT, `${name}.webm`);
	fs.renameSync(path.join(tmpDir, file), dest);
	fs.rmSync(tmpDir, { recursive: true, force: true });
	console.log('clip:', name);
}

(async () => {
	const browser = await chromium.launch();
	const main = await browser.newContext({ viewport: VIEWPORT });
	const page = await main.newPage();
	page.on('console', (m) => { if (m.type() === 'error') console.log('console error:', m.text()); });
	page.on('pageerror', (e) => console.log('pageerror:', e.message));

	// ── 1. Plan: before ──────────────────────────────────────────
	await page.goto(`${BASE}/planner`, { waitUntil: 'domcontentloaded' });
	await page.waitForSelector('text=New', { timeout: 15000 });
	await page.waitForTimeout(400);
	await shot(page, 1, 'plan-before');

	// ── 2. Plan: drag-to-create (video) ──────────────────────────
	const DAY_WIDTH = 64;
	await recordClip(browser, 'clip-plan-create', VIEWPORT, async (vpage) => {
		await vpage.goto(`${BASE}/planner`, { waitUntil: 'domcontentloaded' });
		await vpage.waitForSelector('div.cursor-crosshair', { timeout: 15000 });
		await vpage.waitForTimeout(300);
		const surface = vpage.locator('div.cursor-crosshair');
		const box = await surface.boundingBox();
		const startX = box.x + DAY_WIDTH * 10.5;
		const y = box.y + 20;
		await vpage.mouse.move(startX, y);
		await vpage.mouse.down();
		await vpage.mouse.move(startX + DAY_WIDTH * 2.5, y, { steps: 12 });
		await vpage.mouse.up();
		await vpage.waitForSelector('input[placeholder="Plan title…"]', { timeout: 5000 });
		await vpage.fill('input[placeholder="Plan title…"]', 'Write intro section');
		// The quick-create popover (.absolute.z-30) has exactly one <select>: category.
		await vpage.locator('div.absolute.z-30 select').first().selectOption({ label: 'Research' });
		await vpage.waitForTimeout(200);
		await vpage.click('button:has-text("Create")');
		await vpage.waitForTimeout(800);
	});

	// ── 3. Plan: open the new item, set priority (one shot covers both
	//    the opened panel and the priority flag) ─────────────────────
	await page.goto(`${BASE}/planner`, { waitUntil: 'domcontentloaded' });
	await page.waitForSelector('text=Write intro section', { timeout: 15000 });
	await page.click('text=Write intro section');
	await page.waitForSelector('text=Start timer', { timeout: 5000 });

	const panelSelects = page.locator('div.fixed select');
	await panelSelects.nth(1).selectOption('high');
	await page.waitForTimeout(300);
	await shot(page, 3, 'plan-priority');

	// ── 4. Track: start the timer from the plan, then let it tick (video
	//    covers both the just-started and ticking states, so no separate
	//    still shot here) ─────────────────────────────────────────────
	await page.click('button:has-text("Start timer")');
	await page.waitForSelector('text=RUNNING', { timeout: 5000 });
	await recordClip(browser, 'clip-timer-ticking', { width: 900, height: 700 }, async (vpage) => {
		await vpage.goto(`${BASE}/planner`, { waitUntil: 'domcontentloaded' });
		await vpage.waitForSelector('text=Write intro section', { timeout: 15000 });
		await vpage.click('text=Write intro section');
		await vpage.waitForSelector('text=RUNNING', { timeout: 8000 });
		await vpage.waitForTimeout(4500);
	});

	// ── 5. Recorder: active timer visible on the dashboard ────────
	await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' });
	await page.waitForSelector('text=Active Timers', { timeout: 15000 });
	await page.waitForTimeout(500);
	await shot(page, 5, 'recorder-active');

	// ── 6. Recorder: stop it, see the plan link, close it out ─────
	await page.click('button[title="Stop"]');
	await page.waitForSelector('text=Fulfilling plan', { timeout: 5000 });
	await shot(page, 6, 'recorder-stop-dialog');
	await page.fill('textarea[placeholder="What did you work on?"]', 'Outlined the introduction and skimmed three related papers.');
	await page.click('label:has-text("Mark plan complete") input[type="checkbox"]');
	await page.click('button:has-text("Save & Log")');
	await page.waitForTimeout(1200);
	await shot(page, 7, 'recorder-after');

	// ── 7. Analyze ─────────────────────────────────────────────────
	await page.goto(`${BASE}/analytics`, { waitUntil: 'domcontentloaded' });
	await page.waitForTimeout(1200);
	await shot(page, 8, 'analytics-overview');

	// ── 8. Ask: a real chat exchange ────────────────────────────────
	await page.goto(`${BASE}/chat`, { waitUntil: 'domcontentloaded' });
	await page.waitForSelector('textarea[placeholder="Ask about your productivity data..."]', { timeout: 15000 });
	await page.fill('textarea[placeholder="Ask about your productivity data..."]', 'How much time have I spent on Research this month?');
	await page.keyboard.press('Enter');
	await page.waitForSelector('text=Send this to Claude?', { timeout: 10000 });
	await shot(page, 9, 'chat-approval');
	await page.click('button:has-text("Send to Claude")');
	await page.waitForSelector('text=Working', { timeout: 5000 }).catch(() => {});
	// Real API round-trip -- give it real time, then wait for the loading
	// indicator to disappear rather than a fixed guess.
	await page.waitForSelector('text=Claude is thinking', { state: 'detached', timeout: 45000 }).catch(() => {});
	await page.waitForTimeout(1500);
	await shot(page, 10, 'chat-answer');

	await browser.close();
	console.log('Done. Assets in', OUT);
})();
