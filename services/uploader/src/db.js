/**
 * Database client for TikTok Uploader Service
 */

const { Pool } = require('pg');
const config = require('./config');

const pool = new Pool({
  host: config.postgres.host,
  port: config.postgres.port,
  user: config.postgres.user,
  password: config.postgres.password,
  database: config.postgres.database,
  max: 10,
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 5000,
});

/**
 * Upload status enum (matches Python models)
 */
const UploadStatus = {
  PENDING: 'pending',
  UPLOADING: 'uploading',
  SUCCESS: 'success',
  FAILED: 'failed',
  MANUAL_REQUIRED: 'manual_required',
};

/**
 * Get video details by ID
 */
async function getVideo(videoId) {
  const result = await pool.query(
    `SELECT v.*, a.script_id, s.story_id, s.part_number, s.total_parts, s.hook, s.content, s.cta,
            st.title as story_title, st.subreddit
     FROM videos v
     JOIN audio a ON v.audio_id = a.id
     JOIN scripts s ON a.script_id = s.id
     JOIN stories st ON s.story_id = st.id
     WHERE v.id = $1`,
    [videoId]
  );
  return result.rows[0];
}

/**
 * Get or create upload record
 */
async function getOrCreateUpload(videoId, platform = 'tiktok') {
  // Check for existing upload
  const existing = await pool.query(
    'SELECT * FROM uploads WHERE video_id = $1 AND platform = $2',
    [videoId, platform]
  );

  if (existing.rows.length > 0) {
    return existing.rows[0];
  }

  // Create new upload record
  const result = await pool.query(
    `INSERT INTO uploads (video_id, platform, status, retry_count, created_at)
     VALUES ($1, $2, $3, 0, NOW())
     RETURNING *`,
    [videoId, platform, UploadStatus.PENDING]
  );

  return result.rows[0];
}

/**
 * Update upload status
 */
async function updateUploadStatus(uploadId, status, extras = {}) {
  const setClauses = ['status = $2'];
  const values = [uploadId, status];
  let paramIndex = 3;

  if (extras.platformVideoId) {
    setClauses.push(`platform_video_id = $${paramIndex++}`);
    values.push(extras.platformVideoId);
  }

  if (extras.platformUrl) {
    setClauses.push(`platform_url = $${paramIndex++}`);
    values.push(extras.platformUrl);
  }

  if (extras.errorMessage) {
    setClauses.push(`error_message = $${paramIndex++}`);
    values.push(extras.errorMessage);
  }

  if (extras.description) {
    setClauses.push(`description = $${paramIndex++}`);
    values.push(extras.description);
  }

  if (status === UploadStatus.SUCCESS) {
    setClauses.push(`uploaded_at = NOW()`);
  }

  const query = `UPDATE uploads SET ${setClauses.join(', ')} WHERE id = $1 RETURNING *`;
  const result = await pool.query(query, values);
  return result.rows[0];
}

/**
 * Increment retry count
 */
async function incrementRetryCount(uploadId) {
  const result = await pool.query(
    'UPDATE uploads SET retry_count = retry_count + 1 WHERE id = $1 RETURNING *',
    [uploadId]
  );
  return result.rows[0];
}

/**
 * Update story status
 */
async function updateStoryStatus(storyId, status) {
  await pool.query(
    'UPDATE stories SET status = $1, updated_at = NOW() WHERE id = $2',
    [status, storyId]
  );
}

/**
 * Update batch progress
 */
async function updateBatchProgress(storyId) {
  // Get batch for story
  const batchResult = await pool.query(
    'SELECT * FROM batches WHERE story_id = $1',
    [storyId]
  );

  if (batchResult.rows.length === 0) return;

  const batch = batchResult.rows[0];

  // Count successful uploads for this story
  const countResult = await pool.query(
    `SELECT COUNT(*) as completed
     FROM uploads u
     JOIN videos v ON u.video_id = v.id
     JOIN audio a ON v.audio_id = a.id
     JOIN scripts s ON a.script_id = s.id
     WHERE s.story_id = $1 AND u.status = $2`,
    [storyId, UploadStatus.SUCCESS]
  );

  const completedParts = parseInt(countResult.rows[0].completed, 10);

  // Determine batch status
  let batchStatus;
  if (completedParts === batch.total_parts) {
    batchStatus = 'completed';
  } else if (completedParts > 0) {
    batchStatus = 'partial';
  } else {
    batchStatus = 'processing';
  }

  await pool.query(
    'UPDATE batches SET completed_parts = $1, status = $2 WHERE id = $3',
    [completedParts, batchStatus, batch.id]
  );
}

/**
 * Health check
 */
async function healthCheck() {
  try {
    await pool.query('SELECT 1');
    return true;
  } catch (error) {
    return false;
  }
}

/**
 * Close pool
 */
async function close() {
  await pool.end();
}

module.exports = {
  pool,
  UploadStatus,
  getVideo,
  getOrCreateUpload,
  updateUploadStatus,
  incrementRetryCount,
  updateStoryStatus,
  updateBatchProgress,
  healthCheck,
  close,
};
