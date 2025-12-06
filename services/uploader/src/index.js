/**
 * TikTok Uploader Service
 *
 * Uses Puppeteer to automate TikTok video uploads with saved browser session.
 * Falls back to manual upload when automation fails.
 */

const express = require('express');
const winston = require('winston');

const app = express();
const PORT = process.env.PORT || 3000;

// Configure logging
const logger = winston.createLogger({
  level: process.env.LOG_LEVEL || 'info',
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.json()
  ),
  transports: [
    new winston.transports.Console()
  ]
});

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({ status: 'healthy', service: 'uploader' });
});

// Placeholder for upload endpoint
app.post('/upload', express.json(), async (req, res) => {
  const { videoId, videoPath, title, description } = req.body;

  logger.info('Upload request received', { videoId, videoPath });

  // TODO: Implement TikTok upload logic with Puppeteer
  res.json({
    status: 'pending',
    message: 'Upload service not yet implemented',
    videoId
  });
});

app.listen(PORT, () => {
  logger.info(`Uploader service listening on port ${PORT}`);
});

module.exports = app;
