// Browser test of the attest dialog (run with run_e2e.py). Needs `playwright-core` (npm) and Google Chrome.
const { chromium } = require('playwright-core');
const fs = require('fs');
const OUT = process.argv[2], PORT = process.argv[3], TOKEN = process.argv[4];
(async () => {
  const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
  const errors = globalThis.__errors = [];
  page.on('console', m => { if (['error', 'warning'].includes(m.type())) errors.push(m.type() + ': ' + m.text()); });
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('response', async r => { if (r.url().includes('/api/') && r.status() >= 400) errors.push('HTTP ' + r.status() + ' ' + r.url().replace(/^.*\/api/, '/api') + ' ' + (await r.text()).slice(0, 200)); });
  await page.goto('http://127.0.0.1:' + PORT + '/?paper=egg#' + TOKEN);
  await page.waitForSelector('table tbody tr');
  // attestations that were made before snapshots existed: the page offers to record them
  console.log('snapshot banner at start:', await page.locator('.banner.info').isVisible());
  await page.click('.banner.info button');
  await page.waitForSelector('.banner.info', { state: 'hidden', timeout: 30000 });
  console.log('snapshots recorded, banner gone');
  await page.selectOption('select[title=filter]', 'all');
  await page.click('tbody tr:has-text("scaling")');
  await page.waitForSelector('#detail-claim h2');
  console.log('detail:', await page.textContent('#detail-claim h2'));
  // attest without having marked it as seen
  await page.keyboard.press('a');
  await page.waitForSelector('dialog[open]');
  await page.selectOption('dialog select >> nth=0', 'yellow');
  console.log('review disabled without reason:', await page.isDisabled('dialog button:text-is("Review")'));
  await page.fill('dialog textarea', 'Read the proof twice');
  await page.click('dialog a.ref:has-text("blind backtranslation")');
  console.log('reason after template:', await page.inputValue('dialog textarea'));
  await page.check('dialog label.check:has-text("C1") input');
  await page.click('dialog button:text-is("Review")');
  await page.waitForSelector('dialog .review');
  console.log('sign disabled before ack:', await page.isDisabled('button:has-text("attestation(s)")'));
  await page.screenshot({ path: OUT + '/e2e_review.png' });
  await page.check('dialog .banner.warn input[type=checkbox]');
  console.log('sign enabled after ack:', !(await page.isDisabled('button:has-text("attestation(s)")')));
  await page.click('button:has-text("attestation(s)")');
  await page.waitForSelector('dialog .job h3:has-text("Done")', { timeout: 30000 });
  console.log('job rows:', (await page.locator('dialog .job tr').allTextContents()).join(' | '));
  await page.screenshot({ path: OUT + '/e2e_done.png' });
  await page.click('dialog button:has-text("Close")');
  await page.waitForSelector('dialog[open]', { state: 'detached', timeout: 2000 }).catch(() => {});
  await page.waitForFunction(() => document.querySelector('#detail-claim .att') && document.querySelector('#detail-claim').textContent.includes('T. Ester'), null, { timeout: 30000 });
  console.log('history shows new attestation:', (await page.locator('#detail-claim ul.plain li').allTextContents()).join(' ; '));
  // seen path: mark seen then attest another claim without the ack box
  await page.click('tbody tr:has-text("colder")');
  await page.waitForSelector('#detail-claim h2:has-text("colder")');
  await page.keyboard.press('v');
  console.log('seen button:', (await page.textContent('#detail-claim .actions button')).trim());
  await page.click('button:has-text("Attest…")');
  await page.fill('dialog textarea', 'second one');
  await page.selectOption('dialog select >> nth=0', 'green');
  await page.click('dialog button:text-is("Review")');
  await page.waitForSelector('dialog .review');
  console.log('ack box shown for seen claim:', await page.locator('dialog .banner.warn input[type=checkbox]').count());
  console.log('sign enabled (seen, no ack needed):', !(await page.isDisabled('button:has-text("attestation(s)")')));
  await page.click('button:has-text("Cancel")');

  // ---- batch: select everything shown, read the unseen ones, sign all with one reason
  await page.selectOption('.selbar select', 'shown');
  console.log('selection:', (await page.textContent('.selbar .muted')).trim());
  const before = await page.textContent('#detail-claim h2');
  await page.click('button:has-text("Next unseen")');
  await page.waitForFunction((b) => document.querySelector('#detail-claim h2') && document.querySelector('#detail-claim h2').textContent !== b, before);
  await page.keyboard.press('v');
  console.log('after reading one more:', (await page.textContent('.selbar .muted')).trim());
  await page.click('button:has-text("selected…")');
  await page.waitForSelector('dialog[open]');
  console.log('dialog targets:', await page.locator('dialog .targets .ref').count());
  await page.selectOption('dialog select >> nth=0', 'green');
  await page.fill('dialog textarea', 'batch: same reason for all');
  await page.click('dialog button:text-is("Review")');
  await page.waitForSelector('dialog .review');
  console.log('unseen warning:', (await page.textContent('dialog .review .banner.warn')).trim().replace(/\s+/g, ' ').slice(0, 60));
  console.log('sign disabled before ack:', await page.isDisabled('button:has-text("attestation(s)")'));
  await page.check('dialog .banner.warn input[type=checkbox]');
  await page.click('button:has-text("attestation(s)")');
  await page.waitForSelector('dialog .job h3:has-text("Done")', { timeout: 60000 });
  const rows = await page.locator('dialog .job tr').allTextContents();
  console.log('batch results:', rows.length, 'rows,', rows.filter(r => r.includes('attested')).length, 'attested');
  await page.screenshot({ path: OUT + '/e2e_batch.png' });
  await page.click('dialog button:has-text("Close")');
  await page.waitForFunction(() => document.querySelector('.selbar .muted').textContent.startsWith('0 selected'), null, { timeout: 30000 });
  console.log('selection cleared after batch:', (await page.textContent('.selbar .muted')).trim());

  // ---- hypotheses: the tab, the detail, attesting one as a known theorem
  await page.click('.tabs button:has-text("Hypotheses")');
  await page.click('.hyplist tbody tr >> nth=0');
  await page.waitForSelector('#detail-hyp h3:has-text("Cited sources")');
  const hypName = (await page.textContent('.hyplist tbody tr >> nth=0')).trim().split(/\s+/)[0];
  console.log('hypothesis:', hypName);
  await page.keyboard.press('v');
  await page.keyboard.press('a');
  await page.waitForSelector('dialog[open]');
  console.log('dialog title:', (await page.textContent('dialog h2')).trim().replace(/\s+/g, ' '));
  await page.selectOption('dialog select >> nth=0', 'green');
  await page.click('dialog button:text-is("Review")');
  await page.waitForSelector('dialog .review');
  console.log('unseen box for a seen hypothesis:', await page.locator('dialog .review .banner.warn').isVisible());
  await page.click('button:has-text("attestation(s)")');
  await page.waitForSelector('dialog .job h3:has-text("Done")', { timeout: 30000 });
  console.log('hyp result:', (await page.locator('dialog .job tr').first().textContent()).trim().replace(/\s+/g, ' '));
  await page.click('dialog button:has-text("Close")');
  await page.waitForFunction((n) => [...document.querySelectorAll('.hyplist tbody tr')].some(r => r.textContent.includes(n) && r.textContent.includes('known theorem')), hypName, { timeout: 30000 });
  console.log('hypothesis now: known theorem');
  await page.keyboard.press('t');

  // ---- background jobs: lock, then verify (the lock file now includes the attestations just made)
  for (const kind of ['lock', 'verify']) {
    await page.selectOption('header select[title^="run"]', kind);
    await page.waitForSelector('section.jobs', { state: 'visible' });
    await page.waitForFunction((k) => [...document.querySelectorAll('section.jobs tbody tr')].some(r => r.textContent.includes(k) && r.textContent.includes('done')), kind, { timeout: 60000 });
    console.log('job ' + kind + ':', (await page.locator('section.jobs pre.joblog').textContent()).trim().split('\n').slice(-1)[0].slice(0, 60));
  }
  await page.screenshot({ path: OUT + '/e2e_jobs.png' });

  // ---- what changed since an attestation: record snapshots, edit the paper on disk, reload, read the diff
  const tex = OUT + '/egg/paper/main.tex';
  fs.writeFileSync(tex, fs.readFileSync(tex, 'utf8').replace('\\label{lem:scaling}', '\\label{lem:scaling} In particular for large eggs.'));
  await page.waitForSelector('.banner.warn:has-text("Files changed on disk")', { timeout: 20000 });
  await page.click('.banner.warn button:has-text("Reload now")');
  await page.waitForFunction(() => !document.querySelector('.loading') || document.querySelector('.loading').style.display === 'none', null, { timeout: 60000 });
  await page.selectOption('select[title=filter]', 'all');
  await page.click('tbody tr:has-text("scaling")');
  await page.waitForSelector('#detail-claim .diffbox ins', { timeout: 30000 });
  console.log('diff shows the inserted text:', (await page.locator('#detail-claim .diffbox ins').allTextContents()).join(' | ').trim());
  await page.screenshot({ path: OUT + '/e2e_diff.png', fullPage: true });
  console.log('console problems:', JSON.stringify(errors));
  if (errors.length) process.exitCode = 1;
  await browser.close();
})().catch(e => { console.error('E2E FAILED', e.message.split('\n')[0]); console.error('collected problems:', JSON.stringify(globalThis.__errors || [])); process.exit(1); });
