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
   * Check if user is logged in
   */
  async isLoggedIn() {
    try {
      await this.page.goto(TIKTOK_HOME_URL, {
        waitUntil: 'networkidle2',
        timeout: 30000,
      });

      // Check for multiple login indicators (TikTok UI changes frequently)
      const loginIndicators = [
        '[data-e2e="top-login-button"]',
        'button[data-e2e="login-button"]',
        'a[href*="/login"]',
        '[class*="login-button"]',
        '[class*="LoginButton"]',
      ];

      // Check for logged-in indicators
      const loggedInIndicators = [
        '[data-e2e="upload-icon"]',
        '[data-e2e="profile-icon"]',
        '[class*="avatar"]',
        '[class*="Avatar"]',
        'a[href*="/upload"]',
      ];

      // First check if we see logged-in indicators
      for (const selector of loggedInIndicators) {
        const element = await this.page.$(selector);
        if (element) {
          this.logger.info('Login check: found logged-in indicator', { selector });
          return true;
        }
      }

      // Then check if we see login prompts (means not logged in)
      for (const selector of loginIndicators) {
        const element = await this.page.$(selector);
        if (element) {
          this.logger.info('Login check: found login button', { selector });
          return false;
        }
      }

      // Check URL - if redirected to login page, not logged in
      const currentUrl = this.page.url();
      if (currentUrl.includes('/login') || currentUrl.includes('login_redirect')) {
        this.logger.info('Login check: redirected to login page');
        return false;
      }

      // If we can't determine, assume NOT logged in to be safe
      this.logger.warn('Login check: could not determine login status, assuming not logged in');
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

    await this.page.goto(TIKTOK_HOME_URL, {
      waitUntil: 'networkidle2',
    });

    const startTime = Date.now();

    while (Date.now() - startTime < timeoutMs) {
      const isLoggedIn = await this.isLoggedIn();
      if (isLoggedIn) {
        // Save cookies after successful login
        const cookies = await session.extractCookies(this.page);
        await session.saveCookies(cookies);
        this.logger.info('Login successful, cookies saved');
        return true;
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

    // Wait for upload iframe or file input
    await this.sleep(3000);

    // Handle the iframe-based uploader
    const frames = this.page.frames();
    let uploadFrame = null;

    for (const frame of frames) {
      const frameUrl = frame.url();
      if (frameUrl.includes('upload') || frameUrl.includes('creator')) {
        uploadFrame = frame;
        break;
      }
    }

    const targetContext = uploadFrame || this.page;

    // Find and interact with file input
    const fileInputSelector = 'input[type="file"]';
    await targetContext.waitForSelector(fileInputSelector, { timeout: 30000 });
    const fileInput = await targetContext.$(fileInputSelector);

    if (!fileInput) {
      throw new Error('Could not find file input element');
    }

    // Upload the video file
    this.logger.info('Uploading video file...');
    await fileInput.uploadFile(videoPath);

    // Wait for upload to process
    await this.waitForUploadProgress(targetContext);

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

      // Clear existing content
      await context.keyboard.down('Control');
      await context.keyboard.press('a');
      await context.keyboard.up('Control');
      await context.keyboard.press('Backspace');

      // Type new caption
      await context.keyboard.type(captionText, { delay: 50 });
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

    const postButtonSelectors = [
      '[data-e2e="post-button"]',
      'button[class*="post"]',
      'button[type="submit"]',
      '[class*="submit-button"]',
    ];

    let postButton = null;
    for (const selector of postButtonSelectors) {
      postButton = await context.$(selector);
      if (postButton) break;
    }

    if (!postButton) {
      throw new Error('Could not find post button');
    }

    // Wait for button to be enabled
    await this.sleep(1000);

    await postButton.click();

    // Wait for post confirmation
    const result = await this.waitForPostConfirmation(context);
    return result;
  }

  /**
   * Wait for post confirmation and extract video ID
   */
  async waitForPostConfirmation(context) {
    this.logger.info('Waiting for post confirmation...');

    const maxWaitTime = 60000;
    const startTime = Date.now();

    while (Date.now() - startTime < maxWaitTime) {
      // Check for success message or redirect
      const currentUrl = this.page.url();

      if (currentUrl.includes('/video/')) {
        // Extract video ID from URL
        const videoIdMatch = currentUrl.match(/\/video\/(\d+)/);
        const platformVideoId = videoIdMatch ? videoIdMatch[1] : null;

        return {
          success: true,
          platformVideoId,
          platformUrl: currentUrl,
        };
      }

      // Check for success indicators
      const successSelectors = [
        '[class*="success"]',
        '[class*="posted"]',
        '[data-e2e="upload-success"]',
      ];

      for (const selector of successSelectors) {
        const element = await context.$(selector);
        if (element) {
          // Try to extract video URL from page
          const videoLink = await context.$('a[href*="/video/"]');
          if (videoLink) {
            const href = await context.evaluate(el => el.href, videoLink);
            const videoIdMatch = href.match(/\/video\/(\d+)/);

            return {
              success: true,
              platformVideoId: videoIdMatch ? videoIdMatch[1] : null,
              platformUrl: href,
            };
          }

          return {
            success: true,
            platformVideoId: null,
            platformUrl: null,
          };
        }
      }

      // Check for error
      const errorSelectors = [
        '[class*="error-message"]',
        '[class*="upload-error"]',
        '[data-e2e="upload-error"]',
      ];

      for (const selector of errorSelectors) {
        const element = await context.$(selector);
        if (element) {
          const errorText = await context.evaluate(
            el => el.textContent,
            element
          );
          throw new Error(`Post failed: ${errorText}`);
        }
      }

      await this.sleep(2000);
    }

    throw new Error('Post confirmation timeout');
  }

  /**
   * Sleep helper
   */
  sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}

module.exports = TikTokUploader;
