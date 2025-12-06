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
const server = app.listen(config.port, () => {
  logger.info(`Uploader service listening on port ${config.port}`);
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
