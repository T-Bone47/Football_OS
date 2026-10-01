const { chromium } = require('playwright');
const fs = require('fs');
const [token, out] = [fs.readFileSync(process.argv[2], 'utf8').trim(), process.argv[3]];
const base = 'http://127.0.0.1:3000';
async function run(reduced) {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, reducedMotion: reduced ? 'reduce' : 'no-preference',
    recordVideo: reduced ? undefined : { dir: out + '/video', size: { width: 1366, height: 900 } } });
  await ctx.addInitScript((t) => sessionStorage.setItem('fios_ops_token', t), token);
  const page = await ctx.newPage();
  const r = { reduced };
  await page.goto(base + '/data-ops', { waitUntil: 'networkidle' });
  r.nav_indicators = await page.$$eval('.nav-indicator', (els) => els.length);
  r.indicator_on_active = await page.$eval('.nav-item.active', (a) => !!a.querySelector('.nav-indicator'));
  r.tab_underlines = await page.$$eval('.ops-tab-underline', (els) => els.length);
  await page.click('[data-testid="tab-runs"]');
  // sample the panel's transform/opacity mid-transition
  r.mid_tab_switch = await page.evaluate(() => new Promise((res) => setTimeout(() => {
    const p = document.querySelector('[role="tabpanel"]'); res(p ? getComputedStyle(p).opacity : null); }, 60)));
  await page.waitForTimeout(600);
  r.runs_panel_visible = await page.evaluate(() => { const p = document.querySelectorAll('[role=tabpanel]'); return [p.length, getComputedStyle(p[0]).opacity, p[0].innerText.slice(0, 40)]; });
  r.underline_under_runs = await page.$eval('[data-testid="tab-runs"]', (b) => !!b.querySelector('.ops-tab-underline'));
  // route change through the sidebar: sample the page wrapper transform mid-transition
  await page.click('[data-testid="nav-link-model-operations"]');
  r.route_samples = await page.evaluate(() => new Promise((res) => {
    const s = []; let n = 0;
    const tick = () => { const el = document.querySelector('.page-transition');
      if (el) { const cs = getComputedStyle(el); s.push([cs.opacity, cs.transform]); }
      if (++n < 12) setTimeout(tick, 30); else res(s); };
    tick(); }));
  await page.waitForLoadState('networkidle'); await page.waitForTimeout(500);
  r.url_after = page.url().replace(base, '');
  r.indicator_moved = await page.$eval('[data-testid="nav-link-model-operations"]', (a) => !!a.querySelector('.nav-indicator'));
  r.page_after_route = await page.evaluate(() => { const w = document.querySelectorAll('.page-transition'); return [w.length, getComputedStyle(w[0]).opacity, getComputedStyle(w[0]).transform, !!document.querySelector('[data-testid=model-ops-page]')]; });
  r.any_transform_during_route = r.route_samples.some(([, t]) => t && t !== 'none');
  // command palette open/close
  await page.keyboard.press('Control+k');
  await page.waitForTimeout(80);
  r.palette_open_opacity = await page.$eval('[data-testid="command-palette"]', (e) => getComputedStyle(e).opacity);
  await page.waitForTimeout(400);
  if (!reduced) await page.screenshot({ path: out + '/command-palette-open.png' });
  await page.keyboard.press('Escape');
  r.palette_still_in_dom_during_exit = !!(await page.$('[data-testid="command-palette"]'));
  await page.waitForTimeout(500);
  r.palette_removed_after_exit = !(await page.$('[data-testid="command-palette"]'));
  r.tabs_present = await page.$$eval('[role=tab]', (e) => e.map((x) => x.dataset.testid)); r.main_text = (await page.innerText('main')).slice(0, 200); if (!reduced && r.tabs_present.includes('tab-health')) { await page.click('[data-testid="tab-health"]'); await page.waitForLoadState('networkidle'); await page.waitForTimeout(1500);
    await page.screenshot({ path: out + '/model-ops-health-motion.png' }); }
  r.overflow = await page.evaluate(() => document.scrollingElement.scrollWidth - innerWidth);
  await ctx.close(); await browser.close();
  return r;
}
(async () => { const res = [await run(false), await run(true)]; console.log(JSON.stringify(res, null, 1)); fs.writeFileSync(out + '/motion_check.json', JSON.stringify(res, null, 1)); })();
