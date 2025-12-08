/**
 * TikTok upload automation using Puppeteer
 */

const puppeteer = require('puppeteer');
const path = require('path');
const fs = require('fs').promises;
const config = require('./config');
const session = require('./session');

const TIKTOK_UPLOAD_URL = 'https://www.tiktok.com/upload';
const TIKTOK_HOME_URL = 'https://www.tiktok.com';

// Debug screenshot directory - use config path
const getDebugPath = (filename) => {
  const dataDir = process.platform === 'win32'
    ? 'C:\\Users\\L\\Desktop\\TikTok Auto\\data'
    : '/data';
  return require('path').join(dataDir, filename);
};

/**
 * TikTok Uploader class
 */
class TikTokUploader {
  constructor(logger) {
    this.logger = logger;
    this.browser = null;
    this.page = null;
  }

  /**
   * Initialize browser instance
   */
  async init() {
    const launchOptions = {
      headless: config.browser.headless ? 'new' : false,
      args: config.browser.args,
      userDataDir: session.getUserDataDir(),
    };

    if (config.browser.executablePath) {
      launchOptions.executablePath = config.browser.executablePath;
    }

    this.logger.info('Launching browser', { headless: config.browser.headless });
    this.browser = await puppeteer.launch(launchOptions);
    this.page = await this.browser.newPage();

    // Set viewport for TikTok desktop experience
    await this.page.setViewport({ width: 1920, height: 1080 });

    // Set user agent to avoid detection
    await this.page.setUserAgent(
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    );

    // Load saved cookies
    const cookies = await session.loadCookies();
    if (cookies.length > 0) {
      await session.applyCookies(this.page, cookies);
      this.logger.info('Loaded saved cookies', { count: cookies.length });
    }
  }

  /**
   * Close browser instance
   */
  async close() {
    if (this.page) {
      // Save cookies before closing
      const cookies = await session.extractCookies(this.page);
      await session.saveCookies(cookies);
      this.logger.info('Saved cookies', { count: cookies.length });
    }

    if (this.browser) {
      await this.browser.close();
      this.browser = null;
      this.page = null;
    }
  }

  /**
   * Check if user is logged in by navigating to the upload page
   * and checking if we can see the file upload input
   */
  async isLoggedIn() {
    try {
      // First check if we have session cookies loaded
      const cookies = await this.page.cookies();
      const tiktokCookies = cookies.filter(c => c.domain.includes('tiktok'));
      const sessionCookies = tiktokCookies.filter(c =>
        c.name.toLowerCase().includes('session') ||
        c.name.toLowerCase().includes('sid_')
      );

      this.logger.info('Login check: cookies status', {
        total: cookies.length,
        tiktok: tiktokCookies.length,
        session: sessionCookies.length
      });

      // Navigate directly to upload page - this is the most reliable check
      this.logger.info('Login check: navigating to upload page...');
      await this.page.goto(TIKTOK_UPLOAD_URL, {
        waitUntil: 'networkidle2',
        timeout: 30000,
      });

      // Wait a moment for page to settle
      await this.sleep(2000);

      const currentUrl = this.page.url();
      this.logger.info('Login check: current URL', { url: currentUrl });

      // If we're on login page, definitely not logged in
      if (currentUrl.includes('/login')) {
        this.logger.info('Login check: redirected to login page - not logged in');
        return false;
      }

      // Check for file input - this means we have creator access
      const fileInput = await this.page.$('input[type="file"]');
      if (fileInput) {
        this.logger.info('Login check: found file input - logged in with creator access');
        return true;
      }

      // Also check in frames
      const frames = this.page.frames();
      for (const frame of frames) {
        try {
          const frameFileInput = await frame.$('input[type="file"]');
          if (frameFileInput) {
            this.logger.info('Login check: found file input in frame - logged in');
            return true;
          }
        } catch (e) {
          // Ignore frame errors
        }
      }

      // If we're on upload page URL but no file input, might need more time
      if (currentUrl.includes('/upload') && !currentUrl.includes('/login')) {
        // Wait longer and try again
        await this.sleep(3000);

        const fileInputRetry = await this.page.$('input[type="file"]');
        if (fileInputRetry) {
          this.logger.info('Login check: found file input on retry - logged in');
          return true;
        }

        // Take debug screenshot
        try {
          await this.page.screenshot({ path: getDebugPath('debug_login_check.png'), fullPage: true });
          this.logger.info('Debug screenshot saved for login check');
        } catch (e) {}
      }

      this.logger.warn('Login check: could not find file input - not logged in or no creator access');
      return false;
    } catch (error) {
      this.logger.error('Login check failed', { error: error.message });
      return false;
    }
  }

  /**
   * Wait for manual login
   */
  async waitForManualLogin(timeoutMs = 300000) {
    this.logger.info('Waiting for manual login...', { timeout: timeoutMs });

    // Navigate to upload page so user logs in with creator permissions
    await this.page.goto(TIKTOK_UPLOAD_URL, {
      waitUntil: 'networkidle2',
    });

    this.logger.info('Please log in to TikTok. Waiting for upload form to appear...');

    const startTime = Date.now();

    while (Date.now() - startTime < timeoutMs) {
      // Check if we can see the upload file input (means fully logged in with creator access)
      try {
        const fileInput = await this.page.$('input[type="file"]');
        if (fileInput) {
          // Save cookies after successful login
          const cookies = await session.extractCookies(this.page);
          await session.saveCookies(cookies);
          this.logger.info('Upload form detected! Login successful, cookies saved');
          return true;
        }
      } catch (err) {
        // Ignore errors, keep waiting
      }

      // Also check frames (TikTok uses iframes)
      const frames = this.page.frames();
      for (const frame of frames) {
        try {
          const fileInput = await frame.$('input[type="file"]');
          if (fileInput) {
            const cookies = await session.extractCookies(this.page);
            await session.saveCookies(cookies);
            this.logger.info('Upload form detected in frame! Login successful, cookies saved');
            return true;
          }
        } catch (err) {
          // Ignore
        }
      }

      await this.sleep(2000);
    }

    throw new Error('Login timeout - manual login required');
  }

  /**
   * Upload video to TikTok
   */
  async uploadVideo(videoPath, options = {}) {
    const {
      title = '',
      description = '',
      hashtags = [],
      visibility = 'public',
    } = options;

    this.logger.info('Starting video upload', {
      videoPath,
      title: title.substring(0, 50),
      hashtagCount: hashtags.length,
    });

    // Verify video file exists
    try {
      await fs.access(videoPath);
    } catch (error) {
      throw new Error(`Video file not found: ${videoPath}`);
    }

    // Navigate to upload page
    await this.page.goto(TIKTOK_UPLOAD_URL, {
      waitUntil: 'networkidle2',
      timeout: 60000,
    });

    // Log current URL for debugging
    const currentUrl = this.page.url();
    this.logger.info('Navigated to upload page', { url: currentUrl });

    // Wait for page to settle
    await this.sleep(3000);

    // Dismiss any notifications and banners before proceeding
    await this.dismissBanners();

    // Take debug screenshot
    try {
      await this.page.screenshot({ path: getDebugPath('debug_upload_page.png'), fullPage: true });
      this.logger.info('Debug screenshot saved to debug_upload_page.png');
    } catch (err) {
      this.logger.warn('Failed to save debug screenshot', { error: err.message });
    }

    // Handle the iframe-based uploader
    const frames = this.page.frames();
    let uploadFrame = null;

    this.logger.info('Checking frames', { frameCount: frames.length });
    for (const frame of frames) {
      const frameUrl = frame.url();
      this.logger.info('Frame URL', { url: frameUrl });
      if (frameUrl.includes('upload') || frameUrl.includes('creator')) {
        uploadFrame = frame;
        break;
      }
    }

    const targetContext = uploadFrame || this.page;

    // Find and interact with file input
    const fileInputSelector = 'input[type="file"]';
    try {
      await targetContext.waitForSelector(fileInputSelector, { timeout: 30000 });
    } catch (err) {
      // Take screenshot on failure
      await this.page.screenshot({ path: getDebugPath('debug_upload_error.png'), fullPage: true });
      this.logger.error('File input not found, screenshot saved', { url: this.page.url() });
      throw err;
    }
    const fileInput = await targetContext.$(fileInputSelector);

    if (!fileInput) {
      throw new Error('Could not find file input element');
    }

    // Upload the video file
    this.logger.info('Uploading video file...');
    await fileInput.uploadFile(videoPath);
    this.logger.info('File input triggered');

    // Wait for upload to start processing
    await this.sleep(5000);

    // Take debug screenshot after file upload
    try {
      await this.page.screenshot({ path: getDebugPath('debug_after_upload.png'), fullPage: true });
      this.logger.info('Debug screenshot after upload saved');
    } catch (err) {
      this.logger.warn('Failed to save debug screenshot after upload', { error: err.message });
    }

    // Wait for upload to process
    await this.waitForUploadProgress(targetContext);

    // Dismiss any modals that appeared during upload (like content checks)
    // Wait a bit longer for the content checks modal to appear
    await this.sleep(3000);
    await this.dismissBanners();

    // Wait and try again - the modal might take time to appear
    await this.sleep(2000);
    await this.dismissContentChecksModal();

    // Fill in caption/description
    await this.fillCaption(targetContext, title, description, hashtags);

    // Set visibility settings
    await this.setVisibility(targetContext, visibility);

    // Click post button
    const result = await this.clickPostButton(targetContext);

    this.logger.info('Upload completed', result);
    return result;
  }

  /**
   * Wait for upload progress to complete
   */
  async waitForUploadProgress(context) {
    this.logger.info('Waiting for video processing...');

    const maxWaitTime = config.tiktok.uploadTimeout;
    const startTime = Date.now();

    while (Date.now() - startTime < maxWaitTime) {
      // Check for success indicators
      const progressSelectors = [
        '[class*="upload-progress"]',
        '[class*="uploading"]',
        '[data-e2e="upload-progress"]',
      ];

      let isUploading = false;
      for (const selector of progressSelectors) {
        const element = await context.$(selector);
        if (element) {
          isUploading = true;
          break;
        }
      }

      // Check for completion indicators
      const completionSelectors = [
        '[class*="caption-editor"]',
        '[class*="post-button"]',
        '[data-e2e="post-button"]',
        'button[type="submit"]',
      ];

      for (const selector of completionSelectors) {
        const element = await context.$(selector);
        if (element) {
          this.logger.info('Video processing complete');
          return;
        }
      }

      if (!isUploading) {
        // Check for error messages
        const errorElement = await context.$('[class*="error"]');
        if (errorElement) {
          const errorText = await context.evaluate(
            el => el.textContent,
            errorElement
          );
          throw new Error(`Upload error: ${errorText}`);
        }
      }

      await this.sleep(2000);
    }

    throw new Error('Upload processing timeout');
  }

  /**
   * Fill in caption with title, description, and hashtags
   */
  async fillCaption(context, title, description, hashtags) {
    this.logger.info('Filling caption...');

    // Build caption text
    const hashtagString = hashtags.map(tag =>
      tag.startsWith('#') ? tag : `#${tag}`
    ).join(' ');

    const captionText = [title, description, hashtagString]
      .filter(Boolean)
      .join('\n\n');

    // Find caption editor
    const captionSelectors = [
      '[data-e2e="caption-editor"]',
      '[class*="caption-input"]',
      '[class*="DraftEditor-root"]',
      '[contenteditable="true"]',
      'div[class*="editor"]',
    ];

    let captionEditor = null;
    for (const selector of captionSelectors) {
      captionEditor = await context.$(selector);
      if (captionEditor) break;
    }

    if (captionEditor) {
      await captionEditor.click();
      await this.sleep(500);

      // Clear existing content - use page.keyboard (frames don't have keyboard property)
      await this.page.keyboard.down('Control');
      await this.page.keyboard.press('a');
      await this.page.keyboard.up('Control');
      await this.page.keyboard.press('Backspace');

      // Type new caption
      await this.page.keyboard.type(captionText, { delay: 50 });
      this.logger.info('Caption filled');
    } else {
      this.logger.warn('Could not find caption editor');
    }
  }

  /**
   * Set video visibility settings
   */
  async setVisibility(context, visibility) {
    this.logger.info('Setting visibility', { visibility });

    // Find visibility dropdown or radio buttons
    const visibilitySelectors = [
      '[data-e2e="privacy-setting"]',
      '[class*="visibility"]',
      '[class*="privacy"]',
    ];

    for (const selector of visibilitySelectors) {
      const element = await context.$(selector);
      if (element) {
        await element.click();
        await this.sleep(500);

        // Select the appropriate option
        const optionText = visibility === 'public' ? 'Everyone' : 'Only me';
        const options = await context.$$('[role="option"], [class*="option"]');

        for (const option of options) {
          const text = await context.evaluate(el => el.textContent, option);
          if (text.toLowerCase().includes(optionText.toLowerCase())) {
            await option.click();
            break;
          }
        }
        break;
      }
    }
  }

  /**
   * Click the post/publish button
   */
  async clickPostButton(context) {
    this.logger.info('Clicking post button...');

    // Final check for modals before clicking Post
    await this.dismissContentChecksModal();

    // Take screenshot before looking for Post button
    try {
      await this.page.screenshot({ path: getDebugPath('debug_before_post_click.png'), fullPage: true });
      this.logger.info('Screenshot saved before Post button click');
    } catch (err) {
      this.logger.warn('Failed to save pre-post screenshot');
    }

    // First, scroll down to make sure Post button is visible
    await this.page.evaluate(() => {
      window.scrollTo(0, document.body.scrollHeight);
    });
    await this.sleep(1000);

    // Try to find Post button by various methods
    const postButtonSelectors = [
      '[data-e2e="post-button"]',
      'button[class*="post"]',
      'button[type="submit"]',
      '[class*="submit-button"]',
      '[class*="Post"]',
    ];

    let postButton = null;
    for (const selector of postButtonSelectors) {
      postButton = await context.$(selector);
      if (postButton) {
        this.logger.info('Found post button via selector', { selector });
        break;
      }
    }

    // If not found by selector, try to find by text content
    if (!postButton) {
      this.logger.info('Searching for Post button by text...');
      const buttons = await this.page.$$('button');
      for (const btn of buttons) {
        const text = await this.page.evaluate(el => el.textContent, btn);
        if (text && text.trim().toLowerCase() === 'post') {
          postButton = btn;
          this.logger.info('Found Post button by text');
          break;
        }
      }
    }

    if (!postButton) {
      // Take screenshot to debug
      await this.page.screenshot({ path: getDebugPath('debug_post_button_error.png'), fullPage: true });
      this.logger.error('Post button not found, screenshot saved');
      throw new Error('Could not find post button');
    }

    // Wait for button to be enabled
    await this.sleep(1000);

    this.logger.info('Clicking Post button NOW...');
    await postButton.click();
    this.logger.info('Post button clicked!');

    // Take screenshot right after clicking
    try {
      await this.sleep(2000);
      await this.page.screenshot({ path: getDebugPath('debug_after_post_click.png'), fullPage: true });
      this.logger.info('Screenshot saved after Post button click');
    } catch (err) {
      this.logger.warn('Failed to save post-click screenshot');
    }

    // Wait for post confirmation
    const result = await this.waitForPostConfirmation(context);
    return result;
  }

  /**
   * Wait for post confirmation and extract video ID
   */
  async waitForPostConfirmation(context) {
    this.logger.info('Waiting for post confirmation...');

    const maxWaitTime = 120000; // Increased to 2 minutes for video processing
    const startTime = Date.now();
    let lastScreenshotTime = 0;

    while (Date.now() - startTime < maxWaitTime) {
      // Take periodic debug screenshots
      if (Date.now() - lastScreenshotTime > 15000) {
        try {
          const elapsed = Math.floor((Date.now() - startTime) / 1000);
          await this.page.screenshot({ path: getDebugPath(`debug_waiting_${elapsed}s.png`), fullPage: true });
          this.logger.info(`Debug screenshot at ${elapsed}s saved`);
          lastScreenshotTime = Date.now();
        } catch (e) {}
      }

      // Check for success message or redirect
      const currentUrl = this.page.url();
      this.logger.info('Checking URL for video redirect...', { url: currentUrl.substring(0, 80) });

      if (currentUrl.includes('/video/')) {
        // Extract video ID from URL
        const videoIdMatch = currentUrl.match(/\/video\/(\d+)/);
        const platformVideoId = videoIdMatch ? videoIdMatch[1] : null;

        this.logger.info('SUCCESS: Redirected to video page!', { platformVideoId });
        return {
          success: true,
          platformVideoId,
          platformUrl: currentUrl,
        };
      }

      // Check for video link on the page (TikTok sometimes shows a link instead of redirecting)
      try {
        const videoLink = await this.page.$('a[href*="/video/"]');
        if (videoLink) {
          const href = await this.page.evaluate(el => el.href, videoLink);
          if (href && href.includes('/video/')) {
            const videoIdMatch = href.match(/\/video\/(\d+)/);
            if (videoIdMatch) {
              this.logger.info('SUCCESS: Found video link on page!', { href });
              return {
                success: true,
                platformVideoId: videoIdMatch[1],
                platformUrl: href,
              };
            }
          }
        }
      } catch (e) {
        // Continue checking
      }

      // Handle "Continue to post?" modal - click "Post now" to skip content check
      await this.handleContinueToPostModal();

      // Check for "Your video is being uploaded" or "Processing" messages (not success yet)
      const processingSelectors = [
        '[class*="processing"]',
        '[class*="uploading"]',
        '[class*="progress"]',
      ];

      let isStillProcessing = false;
      for (const selector of processingSelectors) {
        const element = await this.page.$(selector);
        if (element) {
          this.logger.info('Video still processing...', { selector });
          isStillProcessing = true;
          break;
        }
      }

      // Check for error messages
      const errorSelectors = [
        '[class*="error-message"]',
        '[class*="upload-error"]',
        '[data-e2e="upload-error"]',
        '[class*="failed"]',
      ];

      for (const selector of errorSelectors) {
        const element = await this.page.$(selector);
        if (element) {
          const errorText = await this.page.evaluate(
            el => el.textContent,
            element
          );
          this.logger.error('Upload error detected', { errorText });
          await this.page.screenshot({ path: getDebugPath('debug_upload_failed.png'), fullPage: true });
          throw new Error(`Post failed: ${errorText}`);
        }
      }

      // Check if we're back on the upload page (means post failed silently)
      if (currentUrl.includes('/upload') && !isStillProcessing) {
        // Check if the upload form is empty (video cleared)
        const fileInput = await this.page.$('input[type="file"]');
        const uploadPrompt = await this.page.$('[class*="upload-card"]');
        if (fileInput && uploadPrompt) {
          // We're back to upload page with empty form - something went wrong
          const elapsed = Math.floor((Date.now() - startTime) / 1000);
          if (elapsed > 30) {
            this.logger.warn('Back on upload page with empty form - post may have failed');
            await this.page.screenshot({ path: getDebugPath('debug_back_to_upload.png'), fullPage: true });
          }
        }
      }

      await this.sleep(3000);
    }

    // Timeout - take final screenshot
    await this.page.screenshot({ path: getDebugPath('debug_post_timeout.png'), fullPage: true });
    this.logger.error('Post confirmation timeout - no video URL found');
    throw new Error('Post confirmation timeout - video URL not found. Check debug screenshots.');
  }

  /**
   * Dismiss banners and notifications that might block interaction
   */
  async dismissBanners() {
    this.logger.info('Checking for banners to dismiss...');

    // Take debug screenshot before dismissing
    try {
      await this.page.screenshot({ path: getDebugPath('debug_before_dismiss.png'), fullPage: true });
    } catch (e) {}

    // 1. Dismiss cookie consent banner first (at bottom of page)
    try {
      const buttons = await this.page.$$('button');
      for (const btn of buttons) {
        const text = await this.page.evaluate(el => el.textContent, btn);
        if (text && text.trim().toLowerCase() === 'allow all') {
          await btn.click();
          this.logger.info('Dismissed cookie consent banner');
          await this.sleep(1500);
          break;
        }
      }
    } catch (err) {
      this.logger.info('No cookie banner or already dismissed');
    }

    // 2. Handle "Discard this post?" modal FIRST - this blocks everything
    // The modal has "Not now" and "Discard" buttons
    await this.dismissDiscardModal();

    // 3. Dismiss "unsaved editing" notification - click Discard on top banner
    try {
      let buttons = await this.page.$$('button');
      for (const btn of buttons) {
        const text = await this.page.evaluate(el => el.textContent, btn);
        // Look for "Discard" text in the top banner (not in modal)
        if (text && text.trim().toLowerCase() === 'discard') {
          // Check if this is in the top notification bar (not a modal)
          const rect = await this.page.evaluate(el => {
            const r = el.getBoundingClientRect();
            return { top: r.top, left: r.left };
          }, btn);

          // Top banner is usually at the top (y < 200)
          if (rect.top < 200) {
            await btn.click();
            this.logger.info('Clicked Discard on top notification bar');
            await this.sleep(1500);
            // Check if a confirmation modal appeared
            await this.dismissDiscardModal();
            break;
          }
        }
      }
    } catch (err) {
      this.logger.info('No unsaved editing notification');
    }

    // 4. Handle "Turn on automatic content checks?" modal - click "Turn on"
    try {
      const buttons = await this.page.$$('button');
      for (const btn of buttons) {
        const text = await this.page.evaluate(el => el.textContent, btn);
        if (text && text.trim().toLowerCase() === 'turn on') {
          await btn.click();
          this.logger.info('Dismissed content checks modal - clicked Turn on');
          await this.sleep(1500);
          break;
        }
      }
    } catch (err) {
      this.logger.info('No content checks modal');
    }

    // 5. Double-check: dismiss any remaining modals/popups
    try {
      const closeSelectors = [
        '[aria-label="Close"]',
        '[class*="close-button"]',
        'button[class*="close"]',
      ];

      for (const selector of closeSelectors) {
        const closeBtn = await this.page.$(selector);
        if (closeBtn) {
          await closeBtn.click();
          this.logger.info('Dismissed popup via close button', { selector });
          await this.sleep(500);
        }
      }
    } catch (err) {
      // Ignore
    }

    await this.sleep(1000);
  }

  /**
   * Handle "Continue to post?" modal - click "Post now" to skip waiting for content check
   */
  async handleContinueToPostModal() {
    try {
      const pageContent = await this.page.content();
      if (pageContent.includes('Continue to post?') || pageContent.includes('continue posting before the check')) {
        this.logger.info('Found "Continue to post?" modal - clicking Post now');

        const buttons = await this.page.$$('button');
        for (const btn of buttons) {
          const text = await this.page.evaluate(el => el.textContent, btn);
          const normalized = text ? text.trim().toLowerCase() : '';

          if (normalized === 'post now') {
            this.logger.info('Clicking "Post now" button to skip content check');
            await btn.click();
            await this.sleep(3000);
            return true;
          }
        }
      }
    } catch (err) {
      this.logger.info('No "Continue to post?" modal or error:', err.message);
    }
    return false;
  }

  /**
   * Specifically handle "Discard this post?" confirmation modal
   */
  async dismissDiscardModal() {
    try {
      // Look for modal with "Discard this post?" text
      const pageContent = await this.page.content();
      if (pageContent.includes('Discard this post?') || pageContent.includes('discarded permanently')) {
        this.logger.info('Found "Discard this post?" modal');

        // Find all buttons and look for the red Discard button
        const buttons = await this.page.$$('button');
        for (const btn of buttons) {
          const text = await this.page.evaluate(el => el.textContent, btn);
          const normalized = text ? text.trim().toLowerCase() : '';

          // Click the Discard button (usually red/styled differently)
          if (normalized === 'discard') {
            // Check if it's the modal button (not top bar button)
            const rect = await this.page.evaluate(el => {
              const r = el.getBoundingClientRect();
              return { top: r.top };
            }, btn);

            // Modal buttons are usually in the middle of the screen (y > 200)
            if (rect.top > 200) {
              this.logger.info('Clicking Discard button in modal');
              await btn.click();
              await this.sleep(2000);
              return true;
            }
          }
        }
      }
    } catch (err) {
      this.logger.info('No discard modal or error handling it:', err.message);
    }
    return false;
  }

  /**
   * Specifically handle the "Turn on automatic content checks?" modal
   * This modal often appears after video upload and blocks the Post button
   */
  async dismissContentChecksModal() {
    this.logger.info('Looking for content checks modal...');

    // Try up to 5 times with waits in between
    for (let attempt = 0; attempt < 5; attempt++) {
      try {
        // Take a screenshot to see current state
        if (attempt > 0) {
          await this.page.screenshot({ path: getDebugPath(`debug_content_modal_attempt_${attempt}.png`), fullPage: true });
        }

        // Get all buttons on the page
        const buttons = await this.page.$$('button');
        this.logger.info(`Found ${buttons.length} buttons on attempt ${attempt + 1}`);

        for (const btn of buttons) {
          try {
            const text = await this.page.evaluate(el => el.textContent, btn);
            const normalizedText = text ? text.trim().toLowerCase() : '';

            // Log all button texts for debugging
            if (text && text.trim()) {
              this.logger.info(`Button text: "${text.trim()}"`);
            }

            // Match "Turn on" button - use includes for flexibility
            if (normalizedText === 'turn on' || normalizedText.includes('turn on')) {
              this.logger.info('Found "Turn on" button, clicking...');
              await btn.click();
              this.logger.info('Clicked "Turn on" button successfully');
              await this.sleep(2000);
              return true;
            }
          } catch (btnErr) {
            // Button may have been removed, continue
          }
        }

        // Also try to find by aria-label or other attributes
        const turnOnByAttr = await this.page.$('button[aria-label*="Turn on"]');
        if (turnOnByAttr) {
          this.logger.info('Found Turn on button by aria-label');
          await turnOnByAttr.click();
          await this.sleep(2000);
          return true;
        }

        // Check for modal and try Cancel as fallback
        const modalTitle = await this.page.$('div[class*="modal"]');
        if (modalTitle) {
          this.logger.info('Modal detected, looking for any dismiss button...');
          for (const btn of buttons) {
            try {
              const text = await this.page.evaluate(el => el.textContent, btn);
              const normalizedText = text ? text.trim().toLowerCase() : '';
              if (normalizedText === 'cancel' || normalizedText === 'close' || normalizedText === 'not now') {
                this.logger.info(`Found fallback button: "${text.trim()}", clicking...`);
                await btn.click();
                await this.sleep(2000);
                return true;
              }
            } catch (btnErr) {
              continue;
            }
          }
        }

        this.logger.info(`No content checks modal found on attempt ${attempt + 1}`);
        await this.sleep(1000);

      } catch (err) {
        this.logger.warn(`Error on attempt ${attempt + 1}: ${err.message}`);
      }
    }

    this.logger.info('Content checks modal handling complete');
    return false;
  }

  /**
   * Sleep helper
   */
  sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}

module.exports = TikTokUploader;
