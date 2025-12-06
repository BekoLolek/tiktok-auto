/**
 * Tests for TikTok Uploader Service
 */

const request = require('supertest');

// Mock dependencies before requiring app
jest.mock('puppeteer');
jest.mock('pg');

const puppeteer = require('puppeteer');
const { Pool } = require('pg');

// Mock database pool
const mockQuery = jest.fn();
const mockEnd = jest.fn();
Pool.mockImplementation(() => ({
  query: mockQuery,
  end: mockEnd,
}));

// Mock puppeteer browser and page
const mockPage = {
  setViewport: jest.fn(),
  setUserAgent: jest.fn(),
  setCookie: jest.fn(),
  cookies: jest.fn().mockResolvedValue([]),
  goto: jest.fn(),
  $: jest.fn(),
  $$: jest.fn().mockResolvedValue([]),
  frames: jest.fn().mockReturnValue([]),
  url: jest.fn().mockReturnValue('https://www.tiktok.com'),
  waitForSelector: jest.fn(),
  keyboard: {
    down: jest.fn(),
    up: jest.fn(),
    press: jest.fn(),
    type: jest.fn(),
  },
  evaluate: jest.fn(),
};

const mockBrowser = {
  newPage: jest.fn().mockResolvedValue(mockPage),
  close: jest.fn(),
};

puppeteer.launch = jest.fn().mockResolvedValue(mockBrowser);

// Mock fs for cookie file access
jest.mock('fs', () => ({
  promises: {
    readFile: jest.fn().mockRejectedValue({ code: 'ENOENT' }),
    writeFile: jest.fn().mockResolvedValue(),
    mkdir: jest.fn().mockResolvedValue(),
    access: jest.fn().mockResolvedValue(),
  },
}));

// Now require the app
const app = require('../src/index');

describe('TikTok Uploader Service', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockQuery.mockReset();
  });

  describe('GET /health', () => {
    it('should return healthy status when database is connected', async () => {
      mockQuery.mockResolvedValue({ rows: [{ '?column?': 1 }] });

      const response = await request(app).get('/health');

      expect(response.status).toBe(200);
      expect(response.body.status).toBe('healthy');
      expect(response.body.service).toBe('uploader');
      expect(response.body.database).toBe('connected');
    });

    it('should return degraded status when database is disconnected', async () => {
      mockQuery.mockRejectedValue(new Error('Connection failed'));

      const response = await request(app).get('/health');

      expect(response.status).toBe(200);
      expect(response.body.status).toBe('degraded');
      expect(response.body.database).toBe('disconnected');
    });
  });

  describe('POST /upload', () => {
    const validRequest = {
      videoId: '550e8400-e29b-41d4-a716-446655440000',
      videoPath: '/data/videos/test.mp4',
      title: 'Test Video',
      description: 'Test Description',
      hashtags: ['test', 'video'],
    };

    it('should return 400 if videoId is missing', async () => {
      const response = await request(app)
        .post('/upload')
        .send({ videoPath: '/path/to/video.mp4' });

      expect(response.status).toBe(400);
      expect(response.body.message).toBe('videoId and videoPath are required');
    });

    it('should return 400 if videoPath is missing', async () => {
      const response = await request(app)
        .post('/upload')
        .send({ videoId: '550e8400-e29b-41d4-a716-446655440000' });

      expect(response.status).toBe(400);
      expect(response.body.message).toBe('videoId and videoPath are required');
    });

    it('should return 404 if video not found in database', async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .post('/upload')
        .send(validRequest);

      expect(response.status).toBe(404);
      expect(response.body.message).toBe('Video not found');
    });

    it('should return manual_required when max retries exceeded', async () => {
      // Mock video query
      mockQuery.mockResolvedValueOnce({
        rows: [{
          id: validRequest.videoId,
          file_path: '/data/videos/test.mp4',
          story_id: '123',
          story_title: 'Test Story',
          subreddit: 'stories',
          part_number: 1,
          total_parts: 1,
        }],
      });

      // Mock upload query - existing with max retries
      mockQuery.mockResolvedValueOnce({
        rows: [{
          id: 'upload-123',
          video_id: validRequest.videoId,
          retry_count: 3,
          status: 'failed',
        }],
      });

      // Mock update status
      mockQuery.mockResolvedValueOnce({
        rows: [{
          id: 'upload-123',
          status: 'manual_required',
        }],
      });

      const response = await request(app)
        .post('/upload')
        .send(validRequest);

      expect(response.status).toBe(200);
      expect(response.body.status).toBe('manual_required');
      expect(response.body.message).toContain('Max retries exceeded');
    });

    it('should return manual_required when not logged in', async () => {
      // Mock video query
      mockQuery.mockResolvedValueOnce({
        rows: [{
          id: validRequest.videoId,
          file_path: '/data/videos/test.mp4',
          story_id: '123',
          story_title: 'Test Story',
          subreddit: 'stories',
          part_number: 1,
          total_parts: 1,
        }],
      });

      // Mock upload query - no existing upload
      mockQuery.mockResolvedValueOnce({ rows: [] });

      // Mock create upload
      mockQuery.mockResolvedValueOnce({
        rows: [{
          id: 'upload-123',
          video_id: validRequest.videoId,
          retry_count: 0,
          status: 'pending',
        }],
      });

      // Mock status update to uploading
      mockQuery.mockResolvedValueOnce({ rows: [{ id: 'upload-123' }] });

      // Mock login check - found login button (not logged in)
      mockPage.$.mockImplementation((selector) => {
        if (selector === '[data-e2e="top-login-button"]') {
          return Promise.resolve({ click: jest.fn() }); // Login button exists = not logged in
        }
        return Promise.resolve(null);
      });

      // Mock status update to manual required
      mockQuery.mockResolvedValueOnce({ rows: [{ id: 'upload-123' }] });

      const response = await request(app)
        .post('/upload')
        .send(validRequest);

      expect(response.status).toBe(200);
      expect(response.body.status).toBe('manual_required');
      expect(response.body.message).toContain('Login required');
    });
  });

  describe('POST /retry/:uploadId', () => {
    it('should reset upload status for retry', async () => {
      mockQuery.mockResolvedValue({
        rows: [{
          id: 'upload-123',
          status: 'pending',
        }],
      });

      const response = await request(app)
        .post('/retry/upload-123');

      expect(response.status).toBe(200);
      expect(response.body.status).toBe('pending');
      expect(response.body.message).toBe('Upload queued for retry');
    });

    it('should return 404 if upload not found', async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .post('/retry/nonexistent');

      expect(response.status).toBe(404);
      expect(response.body.message).toBe('Upload not found');
    });
  });

  describe('GET /status/:uploadId', () => {
    it('should return upload status', async () => {
      mockQuery.mockResolvedValue({
        rows: [{
          id: 'upload-123',
          video_id: 'video-123',
          status: 'success',
          platform_video_id: '12345',
          platform_url: 'https://tiktok.com/@user/video/12345',
        }],
      });

      const response = await request(app)
        .get('/status/upload-123');

      expect(response.status).toBe(200);
      expect(response.body.status).toBe('success');
      expect(response.body.upload.platform_video_id).toBe('12345');
    });

    it('should return 404 if upload not found', async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get('/status/nonexistent');

      expect(response.status).toBe(404);
      expect(response.body.message).toBe('Upload not found');
    });
  });

  describe('GET /login-status', () => {
    it('should return logged in status when session is valid', async () => {
      // Mock no login button (logged in)
      mockPage.$.mockResolvedValue(null);

      const response = await request(app)
        .get('/login-status');

      expect(response.status).toBe(200);
      expect(response.body.loggedIn).toBe(true);
    });

    it('should return not logged in when login button present', async () => {
      // Mock login button present (not logged in)
      mockPage.$.mockImplementation((selector) => {
        if (selector === '[data-e2e="top-login-button"]') {
          return Promise.resolve({ click: jest.fn() });
        }
        return Promise.resolve(null);
      });

      const response = await request(app)
        .get('/login-status');

      expect(response.status).toBe(200);
      expect(response.body.loggedIn).toBe(false);
    });
  });
});

describe('Config', () => {
  const config = require('../src/config');

  it('should have default values', () => {
    expect(config.port).toBe(3000);
    expect(config.postgres.host).toBe('localhost');
    expect(config.tiktok.maxRetries).toBe(3);
    expect(config.browser.headless).toBe(true);
  });
});

describe('Session Management', () => {
  const session = require('../src/session');

  describe('hasValidSession', () => {
    it('should return false for empty cookies', () => {
      expect(session.hasValidSession([])).toBe(false);
      expect(session.hasValidSession(null)).toBe(false);
    });

    it('should return true when session cookies present', () => {
      const cookies = [
        { name: 'sessionid', value: 'abc123', expires: Date.now() / 1000 + 3600 },
        { name: 'other', value: 'xyz' },
      ];
      expect(session.hasValidSession(cookies)).toBe(true);
    });

    it('should return true for sid_tt cookie', () => {
      const cookies = [
        { name: 'sid_tt', value: 'abc123' },
      ];
      expect(session.hasValidSession(cookies)).toBe(true);
    });
  });

  describe('areCookiesExpired', () => {
    it('should return true for empty cookies', () => {
      expect(session.areCookiesExpired([])).toBe(true);
      expect(session.areCookiesExpired(null)).toBe(true);
    });

    it('should return false for valid non-expired cookies', () => {
      const cookies = [
        { name: 'sessionid', value: 'abc', expires: Date.now() / 1000 + 3600 },
      ];
      expect(session.areCookiesExpired(cookies)).toBe(false);
    });

    it('should return true for expired session cookies', () => {
      const cookies = [
        { name: 'sessionid', value: 'abc', expires: Date.now() / 1000 - 3600 },
      ];
      expect(session.areCookiesExpired(cookies)).toBe(true);
    });
  });
});
