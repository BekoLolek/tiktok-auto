/**
 * Session and cookie management for TikTok Uploader
 */

const fs = require('fs').promises;
const path = require('path');
const config = require('./config');

/**
 * Load cookies from file
 */
async function loadCookies() {
  try {
    const cookiesPath = config.tiktok.cookiesPath;
    const data = await fs.readFile(cookiesPath, 'utf8');
    const cookies = JSON.parse(data);
    return Array.isArray(cookies) ? cookies : [];
  } catch (error) {
    if (error.code === 'ENOENT') {
      return [];
    }
    throw error;
  }
}

/**
 * Save cookies to file
 */
async function saveCookies(cookies) {
  const cookiesPath = config.tiktok.cookiesPath;
  const dir = path.dirname(cookiesPath);

  // Ensure directory exists
  await fs.mkdir(dir, { recursive: true });

  await fs.writeFile(cookiesPath, JSON.stringify(cookies, null, 2), 'utf8');
}

/**
 * Apply cookies to browser page
 */
async function applyCookies(page, cookies) {
  if (cookies && cookies.length > 0) {
    await page.setCookie(...cookies);
  }
}

/**
 * Extract cookies from browser page
 */
async function extractCookies(page) {
  return await page.cookies();
}

/**
 * Check if session cookies are valid (has required TikTok auth cookies)
 */
function hasValidSession(cookies) {
  if (!cookies || cookies.length === 0) return false;

  // TikTok auth cookie names to check
  const requiredCookies = ['sessionid', 'sid_tt', 'sessionid_ss'];
  const cookieNames = cookies.map(c => c.name.toLowerCase());

  return requiredCookies.some(required =>
    cookieNames.some(name => name.includes(required))
  );
}

/**
 * Check if cookies are expired
 */
function areCookiesExpired(cookies) {
  if (!cookies || cookies.length === 0) return true;

  const now = Date.now() / 1000;
  const sessionCookies = cookies.filter(c =>
    c.name.toLowerCase().includes('session')
  );

  return sessionCookies.some(c => c.expires && c.expires < now);
}

/**
 * Get user data directory for persistent browser session
 */
function getUserDataDir() {
  return config.tiktok.sessionDir;
}

module.exports = {
  loadCookies,
  saveCookies,
  applyCookies,
  extractCookies,
  hasValidSession,
  areCookiesExpired,
  getUserDataDir,
};
