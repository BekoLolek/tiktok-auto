/**
 * Prometheus metrics for TikTok Uploader service
 */

const client = require('prom-client');

// Create a Registry
const register = new client.Registry();

// Add default metrics (process CPU, memory, etc.)
client.collectDefaultMetrics({ register });

// Custom metrics for uploads
const uploadsTotal = new client.Counter({
  name: 'tiktok_auto_uploads_total',
  help: 'Total number of upload attempts',
  labelNames: ['status'],
  registers: [register],
});

const uploadDuration = new client.Histogram({
  name: 'tiktok_auto_upload_duration_seconds',
  help: 'Time spent uploading to TikTok',
  buckets: [5, 10, 30, 60, 120, 300, 600],
  registers: [register],
});

const loginStatus = new client.Gauge({
  name: 'tiktok_auto_login_status',
  help: 'TikTok login status (1 = logged in, 0 = not logged in)',
  registers: [register],
});

const pendingUploads = new client.Gauge({
  name: 'tiktok_auto_pending_uploads',
  help: 'Number of uploads pending in queue',
  registers: [register],
});

const failedUploads = new client.Gauge({
  name: 'tiktok_auto_failed_uploads',
  help: 'Number of failed uploads awaiting retry',
  registers: [register],
});

const httpRequestsTotal = new client.Counter({
  name: 'tiktok_auto_http_requests_total',
  help: 'Total HTTP requests',
  labelNames: ['method', 'path', 'status'],
  registers: [register],
});

const httpRequestDuration = new client.Histogram({
  name: 'tiktok_auto_http_request_duration_seconds',
  help: 'HTTP request duration',
  labelNames: ['method', 'path'],
  buckets: [0.01, 0.05, 0.1, 0.5, 1, 5, 10],
  registers: [register],
});

// Helper functions
function recordUpload(status) {
  uploadsTotal.labels(status).inc();
}

function startUploadTimer() {
  return uploadDuration.startTimer();
}

function setLoginStatus(isLoggedIn) {
  loginStatus.set(isLoggedIn ? 1 : 0);
}

function setPendingUploads(count) {
  pendingUploads.set(count);
}

function setFailedUploads(count) {
  failedUploads.set(count);
}

function recordHttpRequest(method, path, status, duration) {
  httpRequestsTotal.labels(method, path, status.toString()).inc();
  httpRequestDuration.labels(method, path).observe(duration);
}

// Express middleware for automatic request metrics
function metricsMiddleware(req, res, next) {
  const start = Date.now();

  res.on('finish', () => {
    const duration = (Date.now() - start) / 1000;
    const path = req.route?.path || req.path || 'unknown';
    recordHttpRequest(req.method, path, res.statusCode, duration);
  });

  next();
}

// Get metrics endpoint handler
async function getMetrics(req, res) {
  try {
    res.set('Content-Type', register.contentType);
    res.end(await register.metrics());
  } catch (err) {
    res.status(500).end(err.message);
  }
}

module.exports = {
  register,
  recordUpload,
  startUploadTimer,
  setLoginStatus,
  setPendingUploads,
  setFailedUploads,
  recordHttpRequest,
  metricsMiddleware,
  getMetrics,
};
