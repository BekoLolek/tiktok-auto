/**
 * Export TikTok cookies - opens a browser for you to log in
 */

const puppeteer = require('puppeteer');
const fs = require('fs').promises;
const path = require('path');

const TIKTOK_URL = 'https://www.tiktok.com/upload';

async function exportCookies() {
  const cookiesPath = process.env.TIKTOK_COOKIES_PATH || path.join(__dirname, '../../../data/tiktok_cookies.json');

  console.log('Cookies output path:', cookiesPath);

  let browser = null;

  try {
    console.log('\nLaunching browser...');
    console.log('A browser window will open - please log in to TikTok\n');

    browser = await puppeteer.launch({
      headless: false,
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-blink-features=AutomationControlled',
        '--window-size=1280,800',
      ],
      defaultViewport: null,
    });

    const page = await browser.newPage();

    // Set user agent to avoid detection
    await page.setUserAgent(
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    );

    // Navigate to TikTok upload page
    console.log('Navigating to TikTok...');
    console.log('Please log in when prompted.\n');
    await page.goto(TIKTOK_URL, {
      waitUntil: 'networkidle2',
      timeout: 60000,
    });

    // Wait for user to log in and reach upload page
    console.log('Waiting for you to log in and reach the upload page...');
    console.log('(Looking for file input element)\n');

    // Keep checking for file input (means logged in with upload access)
    let attempts = 0;
    const maxAttempts = 180; // 3 minutes
    let loggedIn = false;

    while (attempts < maxAttempts) {
      try {
        const currentUrl = page.url();
        const fileInput = await page.$('input[type="file"]');

        if (fileInput) {
          console.log('\n✓ Upload form detected! You are logged in.');
          loggedIn = true;
          break;
        }

        // Also check if we're on the upload page without login redirect
        if (currentUrl.includes('/upload') && !currentUrl.includes('login')) {
          console.log('\n✓ On upload page!');
          loggedIn = true;
          break;
        }

        if (attempts % 10 === 0) {
          console.log(`Still waiting... (${Math.floor(attempts / 2)}s) - Current URL: ${currentUrl.substring(0, 50)}...`);
        }

        await new Promise(resolve => setTimeout(resolve, 1000));
        attempts++;
      } catch (err) {
        // Browser might have been closed or page navigated
        if (err.message.includes('Protocol error') || err.message.includes('context')) {
          console.log('\nBrowser navigation detected, continuing...');
          await new Promise(resolve => setTimeout(resolve, 1000));
          attempts++;
        } else {
          throw err;
        }
      }
    }

    if (!loggedIn && attempts >= maxAttempts) {
      console.log('\nTimeout waiting for login. Please try again.');
      await browser.close();
      process.exit(1);
    }

    // Extract all cookies
    const cookies = await page.cookies();
    console.log(`\nExtracted ${cookies.length} cookies`);

    // Filter for TikTok cookies only
    const tiktokCookies = cookies.filter(c =>
      c.domain.includes('tiktok.com')
    );
    console.log(`TikTok cookies: ${tiktokCookies.length}`);

    // Check for session cookies
    const sessionCookies = tiktokCookies.filter(c =>
      c.name.toLowerCase().includes('session') ||
      c.name.toLowerCase().includes('sid_')
    );
    console.log(`Session cookies found: ${sessionCookies.length}`);

    if (sessionCookies.length === 0) {
      console.log('\nWARNING: No session cookies found. Login may have failed.');
    }

    // Save cookies
    const dir = path.dirname(cookiesPath);
    await fs.mkdir(dir, { recursive: true });
    await fs.writeFile(cookiesPath, JSON.stringify(tiktokCookies, null, 2));

    console.log(`\n✓ Cookies saved to: ${cookiesPath}`);
    console.log('\nYou can now close this browser window.');
    console.log('Then restart the uploader service to use the new cookies.');

    // Keep browser open for a moment
    await new Promise(resolve => setTimeout(resolve, 5000));

  } catch (error) {
    console.error('Error:', error.message);
  } finally {
    if (browser) {
      await browser.close().catch(() => {});
    }
  }
}

exportCookies();
