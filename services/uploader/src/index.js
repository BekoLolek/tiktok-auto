/**
 * TikTok Uploader Service
 *
 * Uses Puppeteer to automate TikTok video uploads with saved browser session.
 * Falls back to manual upload when automation fails.
 */

const express = require('express');
const winston = require('winston');
const config = require('./config');
const db = require('./db');
const TikTokUploader = require('./tiktok');
const metrics = require('./metrics');

const app = express();

// Configure logging
const logger = winston.createLogger({
  level: config.logLevel,
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.json()
  ),
  defaultMeta: { service: 'uploader' },
  transports: [new winston.transports.Console()],
});

// Middleware
app.use(express.json());
app.use(metrics.metricsMiddleware);

// Metrics endpoint
app.get('/metrics', metrics.getMetrics);

// Request logging
app.use((req, res, next) => {
  logger.info('Request received', {
    method: req.method,
    path: req.path,
    body: req.method === 'POST' ? req.body : undefined,
  });
  next();
});

// Health check endpoint
app.get('/health', async (req, res) => {
  const dbHealthy = await db.healthCheck();
  res.json({
    status: dbHealthy ? 'healthy' : 'degraded',
    service: 'uploader',
    database: dbHealthy ? 'connected' : 'disconnected',
  });
});

// Test upload endpoint - bypasses database for direct testing
app.post('/test-upload', async (req, res) => {
  const { videoPath, title, description, hashtags } = req.body;

  if (!videoPath) {
    return res.status(400).json({
      status: 'error',
      message: 'videoPath is required',
    });
  }

  logger.info('Test upload request received', { videoPath, title });

  let uploader = null;

  try {
    // Initialize uploader
    uploader = new TikTokUploader(logger);
    await uploader.init();

    // Check if logged in
    const isLoggedIn = await uploader.isLoggedIn();
    metrics.setLoginStatus(isLoggedIn);
    if (!isLoggedIn) {
      logger.warn('Not logged in');
      await uploader.close();
      metrics.recordUpload('manual_required');
      return res.json({
        status: 'manual_required',
        message: 'Login required - please authenticate manually',
      });
    }

    // Perform upload with timing
    const endTimer = metrics.startUploadTimer();
    const result = await uploader.uploadVideo(videoPath, {
      title: title || 'Test Video',
      description: description || 'Test upload',
      hashtags: hashtags || ['test'],
    });
    endTimer();

    await uploader.close();
    metrics.recordUpload('success');

    return res.json({
      status: 'success',
      result,
    });

  } catch (error) {
    logger.error('Test upload failed', { error: error.message, stack: error.stack });
    metrics.recordUpload('failed');

    if (uploader) {
      await uploader.close().catch(() => {});
    }

    return res.status(500).json({
      status: 'error',
      message: error.message,
    });
  }
});

// Login page - shows status and instructions
app.get('/login', async (req, res) => {
  let uploader = null;
  let isLoggedIn = false;
  let error = null;

  try {
    uploader = new TikTokUploader(logger);
    await uploader.init();
    isLoggedIn = await uploader.isLoggedIn();
    await uploader.close();
  } catch (err) {
    error = err.message;
    if (uploader) {
      await uploader.close().catch(() => {});
    }
  }

  res.send(`
    <!DOCTYPE html>
    <html>
    <head>
      <title>TikTok Login Status</title>
      <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
        .status { padding: 20px; border-radius: 8px; margin: 20px 0; }
        .logged-in { background: #d4edda; border: 1px solid #c3e6cb; }
        .logged-out { background: #f8d7da; border: 1px solid #f5c6cb; }
        .error { background: #fff3cd; border: 1px solid #ffeaa7; }
        h1 { color: #333; }
        code { background: #f4f4f4; padding: 2px 6px; border-radius: 4px; }
        pre { background: #f4f4f4; padding: 15px; border-radius: 8px; overflow-x: auto; }
      </style>
    </head>
    <body>
      <h1>TikTok Uploader - Login Status</h1>

      ${error ? `<div class="status error"><strong>Error:</strong> ${error}</div>` : ''}

      <div class="status ${isLoggedIn ? 'logged-in' : 'logged-out'}">
        <strong>Status:</strong> ${isLoggedIn ? '✅ Logged in to TikTok' : '❌ Not logged in'}
      </div>

      ${!isLoggedIn ? `
        <h2>How to Login</h2>
        <p>TikTok requires manual login through a browser. Follow these steps:</p>

        <h3>Option 1: Login locally (recommended)</h3>
        <ol>
          <li>Stop the Docker containers: <code>docker compose down</code></li>
          <li>Run the uploader locally with visible browser:
            <pre>cd services/uploader
npm install
HEADLESS=false node src/index.js</pre>
          </li>
          <li>The browser will open - navigate to tiktok.com and log in</li>
          <li>Your session will be saved automatically</li>
          <li>Stop the local server and restart Docker</li>
        </ol>

        <h3>Option 2: Copy session from your browser</h3>
        <ol>
          <li>Login to TikTok in your regular browser</li>
          <li>Open DevTools (F12) → Application → Cookies</li>
          <li>Copy all TikTok cookies</li>
          <li>Place them in <code>data/session/cookies.json</code></li>
        </ol>
      ` : `
        <p>✅ You're all set! The uploader can now post videos to TikTok.</p>
        <p><a href="/login-status">Check status via API</a></p>
      `}

      <hr>
      <p><a href="/">← Back</a> | <a href="/health">Health Check</a></p>
    </body>
    </html>
  `);
});

// Upload endpoint
app.post('/upload', async (req, res) => {
  const { videoId, videoPath, title, description, hashtags } = req.body;

  if (!videoId || !videoPath) {
    return res.status(400).json({
      status: 'error',
      message: 'videoId and videoPath are required',
    });
  }

  logger.info('Upload request received', { videoId, videoPath });

  let uploader = null;

  try {
    // Get video details from database
    const video = await db.getVideo(videoId);
    if (!video) {
      return res.status(404).json({
        status: 'error',
        message: 'Video not found',
      });
    }

    // Get or create upload record
    const upload = await db.getOrCreateUpload(videoId, 'tiktok');

    // Check retry count
    if (upload.retry_count >= config.tiktok.maxRetries) {
      await db.updateUploadStatus(upload.id, db.UploadStatus.MANUAL_REQUIRED, {
        errorMessage: 'Max retries exceeded',
      });

      return res.json({
        status: 'manual_required',
        message: 'Max retries exceeded, manual upload required',
        uploadId: upload.id,
        videoId,
      });
    }

    // Update status to uploading
    await db.updateUploadStatus(upload.id, db.UploadStatus.UPLOADING);

    // Build caption from video metadata
    const captionTitle = title || video.story_title || '';
    const captionDescription = description || buildDescription(video);
    const captionHashtags = hashtags || buildHashtags(video);

    // Initialize uploader
    uploader = new TikTokUploader(logger);
    await uploader.init();

    // Check if logged in
    const isLoggedIn = await uploader.isLoggedIn();
    if (!isLoggedIn) {
      logger.warn('Not logged in, marking as manual required');

      await db.updateUploadStatus(upload.id, db.UploadStatus.MANUAL_REQUIRED, {
        errorMessage: 'Login required - please authenticate manually',
      });

      await uploader.close();

      return res.json({
        status: 'manual_required',
        message: 'Login required - please authenticate manually',
        uploadId: upload.id,
        videoId,
      });
    }

    // Perform upload
    const result = await uploader.uploadVideo(videoPath, {
      title: captionTitle,
      description: captionDescription,
      hashtags: captionHashtags,
    });

    // Update database with success
    await db.updateUploadStatus(upload.id, db.UploadStatus.SUCCESS, {
      platformVideoId: result.platformVideoId,
      platformUrl: result.platformUrl,
      description: `${captionTitle}\n\n${captionDescription}`,
    });

    // Update story status
    await db.updateStoryStatus(video.story_id, 'completed');

    // Update batch progress
    await db.updateBatchProgress(video.story_id);

    await uploader.close();

    logger.info('Upload successful', {
      videoId,
      uploadId: upload.id,
      platformVideoId: result.platformVideoId,
    });

    res.json({
      status: 'success',
      message: 'Video uploaded successfully',
      uploadId: upload.id,
      videoId,
      platformVideoId: result.platformVideoId,
      platformUrl: result.platformUrl,
    });
  } catch (error) {
    logger.error('Upload failed', {
      videoId,
      error: error.message,
      stack: error.stack,
    });

    if (uploader) {
      await uploader.close().catch(() => {});
    }

    // Handle upload failure
    try {
      const upload = await db.getOrCreateUpload(videoId, 'tiktok');
      await db.incrementRetryCount(upload.id);

      const newRetryCount = upload.retry_count + 1;
      const status =
        newRetryCount >= config.tiktok.maxRetries
          ? db.UploadStatus.MANUAL_REQUIRED
          : db.UploadStatus.FAILED;

      await db.updateUploadStatus(upload.id, status, {
        errorMessage: error.message,
      });

      if (status === db.UploadStatus.MANUAL_REQUIRED) {
        // Update story status to failed
        const video = await db.getVideo(videoId);
        if (video) {
          await db.updateStoryStatus(video.story_id, 'failed');
        }
      }

      res.status(500).json({
        status: status === db.UploadStatus.MANUAL_REQUIRED ? 'manual_required' : 'failed',
        message: error.message,
        uploadId: upload.id,
        videoId,
        retryCount: newRetryCount,
      });
    } catch (dbError) {
      logger.error('Database update failed', { error: dbError.message });
      res.status(500).json({
        status: 'error',
        message: error.message,
        videoId,
      });
    }
  }
});

// Retry endpoint
app.post('/retry/:uploadId', async (req, res) => {
  const { uploadId } = req.params;

  try {
    // Reset upload status for retry
    const upload = await db.pool.query(
      'UPDATE uploads SET status = $1, error_message = NULL WHERE id = $2 RETURNING *',
      [db.UploadStatus.PENDING, uploadId]
    );

    if (upload.rows.length === 0) {
      return res.status(404).json({
        status: 'error',
        message: 'Upload not found',
      });
    }

    res.json({
      status: 'pending',
      message: 'Upload queued for retry',
      uploadId,
    });
  } catch (error) {
    logger.error('Retry failed', { uploadId, error: error.message });
    res.status(500).json({
      status: 'error',
      message: error.message,
    });
  }
});

// Get upload status
app.get('/status/:uploadId', async (req, res) => {
  const { uploadId } = req.params;

  try {
    const result = await db.pool.query('SELECT * FROM uploads WHERE id = $1', [
      uploadId,
    ]);

    if (result.rows.length === 0) {
      return res.status(404).json({
        status: 'error',
        message: 'Upload not found',
      });
    }

    res.json({
      status: 'success',
      upload: result.rows[0],
    });
  } catch (error) {
    logger.error('Status check failed', { uploadId, error: error.message });
    res.status(500).json({
      status: 'error',
      message: error.message,
    });
  }
});

// Login check endpoint (for manual login flow)
app.get('/login-status', async (req, res) => {
  let uploader = null;

  try {
    uploader = new TikTokUploader(logger);
    await uploader.init();

    const isLoggedIn = await uploader.isLoggedIn();
    await uploader.close();

    res.json({
      status: 'success',
      loggedIn: isLoggedIn,
    });
  } catch (error) {
    if (uploader) {
      await uploader.close().catch(() => {});
    }

    logger.error('Login status check failed', { error: error.message });
    res.status(500).json({
      status: 'error',
      message: error.message,
    });
  }
});

// Helper function to build description
function buildDescription(video) {
  const parts = [];

  if (video.part_number && video.total_parts > 1) {
    parts.push(`Part ${video.part_number}/${video.total_parts}`);
  }

  if (video.subreddit) {
    parts.push(`From r/${video.subreddit}`);
  }

  // Add original author credit
  if (video.story_author) {
    parts.push(`by u/${video.story_author}`);
  }

  // Add original post link
  if (video.story_url) {
    parts.push(`\nOriginal: ${video.story_url}`);
  }

  return parts.join(' | ');
}

// Helper function to build hashtags
function buildHashtags(video) {
  const hashtags = ['storytime', 'reddit', 'redditstories'];

  if (video.subreddit) {
    hashtags.push(video.subreddit.toLowerCase().replace(/[^a-z0-9]/g, ''));
  }

  if (video.total_parts > 1) {
    hashtags.push('series', `part${video.part_number}`);
  }

  return hashtags;
}

// Start server
const server = app.listen(config.port, async () => {
  logger.info(`Uploader service listening on port ${config.port}`);

  // Auto-start login flow if running in non-headless mode
  if (!config.browser.headless) {
    logger.info('Non-headless mode detected, starting login flow...');
    logger.info('Will verify upload page access (not just home page login)...');
    let uploader = null;
    try {
      uploader = new TikTokUploader(logger);
      await uploader.init();

      // Always verify upload page access, not just home page login
      // TikTok requires separate authentication for creator/upload access
      logger.info('Checking upload page access...');
      logger.info('Browser opened - please log in to TikTok if prompted.');
      logger.info('Wait until you see the upload form before pressing Ctrl+C.');

      // waitForManualLogin now navigates to upload page and waits for file input
      await uploader.waitForManualLogin(300000);
      logger.info('Upload page access verified! Session saved.');
      logger.info('You can now stop the server (Ctrl+C).');
      await uploader.close();
    } catch (error) {
      logger.error('Login flow failed', { error: error.message });
      if (uploader) {
        await uploader.close().catch(() => {});
      }
    }
  }
});

// Graceful shutdown
process.on('SIGTERM', async () => {
  logger.info('SIGTERM received, shutting down gracefully');
  server.close(async () => {
    await db.close();
    process.exit(0);
  });
});

process.on('SIGINT', async () => {
  logger.info('SIGINT received, shutting down gracefully');
  server.close(async () => {
    await db.close();
    process.exit(0);
  });
});

module.exports = app;
