// Takes the screenshots of the user manual; driven by make_screenshots.py. Each step names the picture it makes.
const { chromium } = require('playwright-core');
const fs = require('fs');
const [OUT, PORT, TOKEN, PROJ] = process.argv.slice(2);
const URL = `http://127.0.0.1:${PORT}/?paper=egg#${TOKEN}`;
const shot = async (page, name, target, clip) => {
  const t = target || page;
  await t.screenshot({ path: `${OUT}/${name}.png`, ...(clip ? { clip } : {}) });
  console.log('wrote', name);
};

(async () => {
  const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ viewport: { width: 1360, height: 800 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  await page.goto(URL);
  await page.waitForSelector('table tbody tr');

  // 01: the first look; attestations from before snapshots existed are offered a snapshot
  await shot(page, '01-overview', null, { x: 0, y: 0, width: 1360, height: 520 });
  await page.click('.banner.info.nosnap button');
  await page.waitForSelector('.banner.info.nosnap', { state: 'hidden', timeout: 30000 });

  // 02: one claim in detail
  await page.selectOption('select[title=filter]', 'all');
  await page.click('tbody tr:has-text("scaling")');
  await page.waitForSelector('#detail-claim h2');
  await page.waitForTimeout(400);
  await shot(page, '02-detail');

  // 03: select the claims without attestation, read one of them (marked as seen)
  await page.selectOption('.selbar select', 'none');
  await page.click('button:has-text("Next unseen")');
  await page.waitForSelector('#detail-claim h2');
  await page.keyboard.press('v');
  await page.waitForTimeout(300);
  await shot(page, '03-selection');

  // 04: the attest dialog, filled in
  await page.click('button:has-text("selected…")');
  await page.waitForSelector('dialog[open]');
  await page.selectOption('dialog select >> nth=0', 'yellow');
  await page.click('dialog a.tpl >> nth=0');
  await page.check('dialog label.check:has-text("C1") input');
  await page.waitForTimeout(300);
  await shot(page, '04-dialog', page.locator('dialog'));

  // 05: a key that is not loaded in the agent
  await page.selectOption('dialog select >> nth=1', 'ksmith');
  await page.waitForTimeout(200);
  await shot(page, '05-key-not-loaded', page.locator('dialog'));
  await page.selectOption('dialog select >> nth=1', 'jdoe');

  // 06: review: what will be signed, with the unseen warning
  await page.click('dialog button:text-is("Review")');
  await page.waitForSelector('dialog .review');
  await page.waitForTimeout(300);
  await shot(page, '06-review', page.locator('dialog'));

  // 07: signed
  await page.check('dialog .review .banner.warn input[type=checkbox]');
  await page.click('button:has-text("attestation(s)")');
  await page.waitForSelector('dialog .job h3:has-text("Done")', { timeout: 30000 });
  await page.waitForTimeout(300);
  await shot(page, '07-done', page.locator('dialog'));
  await page.click('dialog button:has-text("Close")');
  await page.waitForFunction(() => document.querySelector('.selbar .muted').textContent.startsWith('0 selected'), null, { timeout: 30000 });

  // 08: hypotheses
  await page.click('.tabs button:has-text("Hypotheses")');
  await page.click('.hyplist tbody tr >> nth=0');
  await page.waitForSelector('#detail-hyp h3:has-text("Cited sources")');
  await page.waitForTimeout(300);
  await shot(page, '08-hypothesis');
  await page.click('.tabs button:has-text("Claims")');

  // 09: background jobs
  for (const kind of ['lock', 'verify']) {
    await page.selectOption('header select[title^="run"]', kind);
    await page.waitForSelector('section.jobs', { state: 'visible' });
    await page.waitForFunction((k) => [...document.querySelectorAll('section.jobs tbody tr')].some(r => r.textContent.includes(k) && r.textContent.includes('done')), kind, { timeout: 60000 });
  }
  await page.waitForTimeout(300);
  await shot(page, '09-jobs');
  await page.click('section.jobs button:has-text("Hide")');

  // 10: review pack (needs latexmk and pdflatex)
  try {
    await page.click('tbody tr:has-text("scaling")');
    await page.waitForSelector('#detail-claim h2:has-text("scaling")');
    await page.click('#detail-claim button:has-text("Review pack")');
    await page.waitForSelector('section.packview', { state: 'visible', timeout: 120000 });
    await page.waitForTimeout(4000);                                         // the PDF viewer needs a moment
    await shot(page, '10-review-pack', page.locator('section.packview'));
  } catch (e) { console.log('no review pack picture:', e.message.split('\n')[0]); }
  await page.evaluate(() => { document.querySelector('section.packview') && (document.querySelector('section.packview').style.display = 'none'); });
  await page.keyboard.press('Escape');

  // 11: a statement changes on disk after the attestation: what changed
  const tex = PROJ + '/paper/main.tex';
  fs.writeFileSync(tex, fs.readFileSync(tex, 'utf8').replace('\\label{lem:scaling}', '\\label{lem:scaling} In particular for large eggs.'));
  await page.waitForSelector('.banner.warn:has-text("Files changed on disk")', { timeout: 20000 });
  await shot(page, '11-changed-on-disk', page.locator('.banner.warn'));
  await page.click('.banner.warn button:has-text("Reload now")');
  await page.waitForFunction(() => !document.querySelector('.loading') || document.querySelector('.loading').style.display === 'none', null, { timeout: 60000 });
  await page.selectOption('select[title=filter]', 'all');
  await page.click('tbody tr:has-text("scaling")');
  await page.waitForSelector('#detail-claim .diffbox ins', { timeout: 30000 });
  await page.waitForTimeout(400);
  await shot(page, '12-diff');
  await ctx.close();

  // 13/14: a phone
  const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, hasTouch: true, isMobile: true });
  const m = await phone.newPage();
  await m.goto(URL);
  await m.waitForSelector('table tbody tr');
  await m.waitForTimeout(500);
  await shot(m, '13-phone-list');
  await m.locator('tbody tr >> nth=0').locator('td.name').tap();
  await m.waitForSelector('#detail-claim h2');
  await m.locator('#detail-claim button:has-text("Attest")').tap();
  await m.waitForSelector('dialog[open]');
  await m.waitForTimeout(500);
  await shot(m, '14-phone-dialog');
  await browser.close();
})().catch(e => { console.error('FAILED', e.message.split('\n').slice(0, 4).join(' / ')); process.exit(1); });
