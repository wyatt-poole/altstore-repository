#!/usr/bin/env node
// Drives the in-browser patcher at chroma.pw/patch: base_spotify.ipa -> chroma_patched.ipa.
// Env: CHROMA_VER (kit to select, defaults to whatever the page preselects),
//      PATCH_TIMEOUT_MS (default 240000).
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..', '..');
const INPUT = path.join(ROOT, 'base_spotify.ipa');
const OUTPUT = path.join(ROOT, 'chroma_patched.ipa');
const MIN_SIZE = 50 * 1024 * 1024;
const TIMEOUT = Number(process.env.PATCH_TIMEOUT_MS || 240000);
const CHROMA_VER = (process.env.CHROMA_VER || '').trim();

const escape = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

async function pickRadio(page, opener, label) {
  // Both pickers are popovers of role="radio" buttons, opened by the summary button.
  await opener.click();
  const option = page.getByRole('radio', { name: label }).first();
  await option.waitFor({ timeout: 15000 });
  if ((await option.getAttribute('aria-checked')) !== 'true') await option.click();
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
}

async function main() {
  if (!fs.existsSync(INPUT)) throw new Error(`${INPUT} not found`);
  fs.rmSync(OUTPUT, { force: true });

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ acceptDownloads: true });
  const page = await context.newPage();
  page.on('pageerror', e => console.log(`[page error] ${e.message}`));

  try {
    await page.goto('https://chroma.pw/patch', { waitUntil: 'networkidle', timeout: 90000 });

    const kitButton = page.getByRole('button', { name: /^Chroma\s.*for Spotify/i });
    if (CHROMA_VER && !(await kitButton.innerText()).includes(`Chroma ${CHROMA_VER}`)) {
      console.log(`Selecting kit ${CHROMA_VER}`);
      await pickRadio(page, kitButton, new RegExp(`^${escape(CHROMA_VER)}(\\s|$)`));
    }
    const kitText = (await kitButton.innerText()).replace(/\s+/g, ' ');
    console.log(`Kit: ${kitText}`);
    if (CHROMA_VER && !kitText.includes(`Chroma ${CHROMA_VER}`)) throw new Error(`could not select Chroma ${CHROMA_VER}`);

    // Keep Spotify's own icon: the button reads "App icon\n<current icon>".
    const iconButton = page.getByRole('button', { name: /^App icon/i });
    if (!/App icon\s+Spotify\s*$/i.test(await iconButton.innerText())) {
      console.log('Resetting app icon to Spotify');
      await pickRadio(page, iconButton, /^Spotify$/);
    }
    console.log(`Icon: ${(await iconButton.innerText()).replace(/\s+/g, ' ')}`);

    console.log('Loading IPA into the page...');
    await page.locator('input[type="file"]').setInputFiles(INPUT);

    // The page either enables "Patch" or replaces the form with "Can't use this file".
    const patchBtn = page.getByRole('button', { name: /^Patch$/i });
    const rejected = page.getByText(/Can.t use this file/i);
    await Promise.race([
      patchBtn.and(page.locator(':enabled')).waitFor({ timeout: 120000 }),
      rejected.waitFor({ timeout: 120000 }).then(() => { throw new Error('chroma.pw rejected the IPA'); }),
    ]);

    console.log('Patching...');
    await patchBtn.click();

    // When done the page offers an <a download href="blob:..."> link; it does not auto-download.
    const link = page.locator('a[download]').first();
    const failed = page.getByText(/Patching stopped|ran out of memory/i);
    await Promise.race([
      link.waitFor({ timeout: TIMEOUT }),
      failed.waitFor({ timeout: TIMEOUT }).then(() => { throw new Error('chroma.pw reported a patch failure'); }),
    ]);

    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 60000 }),
      link.click(),
    ]);
    await download.saveAs(OUTPUT);

    const size = fs.statSync(OUTPUT).size;
    console.log(`Saved ${OUTPUT} (${(size / 1e6).toFixed(1)} MB, page named it ${download.suggestedFilename()})`);
    if (size < MIN_SIZE) throw new Error(`patched IPA is only ${size} bytes`);
  } catch (err) {
    console.error(`::error::${err.message}`);
    const text = await page.locator('main').innerText().catch(() => '');
    if (text) console.error(`Page said:\n${text.slice(0, 1500)}`);
    await page.screenshot({ path: path.join(ROOT, 'patch_error.png'), fullPage: true }).catch(() => {});
    await browser.close();
    process.exit(1);
  }
  await browser.close();
}

main().catch(err => { console.error(`::error::${err.stack || err}`); process.exit(1); });
