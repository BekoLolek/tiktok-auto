/**
 * Configuration management for TikTok Uploader Service
 */

const config = {
  // Server
  port: parseInt(process.env.PORT || '3000', 10),
  logLevel: process.env.LOG_LEVEL || 'info',

  // Database
  postgres: {
    host: process.env.POSTGRES_HOST || 'localhost',
    port: parseInt(process.env.POSTGRES_PORT || '5432', 10),
    user: process.env.POSTGRES_USER || 'tiktok_auto',
    password: process.env.POSTGRES_PASSWORD || 'devpassword',
    database: process.env.POSTGRES_DB || 'tiktok_auto',
  },

  // Redis
  redis: {
    host: process.env.REDIS_HOST || 'localhost',
    port: parseInt(process.env.REDIS_PORT || '6379', 10),
  },

  // TikTok
  tiktok: {
    cookiesPath: process.env.TIKTOK_COOKIES_PATH || '/data/tiktok_cookies.json',
    sessionDir: process.env.SESSION_DIR || '/app/session',
    uploadTimeout: parseInt(process.env.UPLOAD_TIMEOUT || '300000', 10), // 5 minutes
    maxRetries: parseInt(process.env.MAX_RETRIES || '3', 10),
    retryDelay: parseInt(process.env.RETRY_DELAY || '5000', 10), // 5 seconds
  },

  // Browser
  browser: {
    headless: process.env.BROWSER_HEADLESS !== 'false',
    executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || null,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-accelerated-2d-canvas',
      '--disable-gpu',
      '--window-size=1920,1080',
    ],
  },

  // Email notifications
  smtp: {
    host: process.env.SMTP_HOST || 'smtp.gmail.com',
    port: parseInt(process.env.SMTP_PORT || '587', 10),
    user: process.env.SMTP_USER,
    password: process.env.SMTP_PASSWORD,
  },
  notificationEmail: process.env.NOTIFICATION_EMAIL,
};

module.exports = config;
