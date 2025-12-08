/**
 * Tests for Prometheus metrics module
 */

const request = require('supertest');
const express = require('express');

// Mock prom-client before requiring metrics
jest.mock('prom-client', () => {
  const mockCounter = {
    labels: jest.fn().mockReturnThis(),
    inc: jest.fn(),
  };
  const mockHistogram = {
    labels: jest.fn().mockReturnThis(),
    observe: jest.fn(),
    startTimer: jest.fn(() => jest.fn()),
  };
  const mockGauge = {
    set: jest.fn(),
  };
  const mockRegistry = {
    contentType: 'text/plain; version=0.0.4',
    metrics: jest.fn().mockResolvedValue('# HELP test_metric Test metric\ntest_metric 1'),
  };

  return {
    Registry: jest.fn(() => mockRegistry),
    Counter: jest.fn(() => mockCounter),
    Histogram: jest.fn(() => mockHistogram),
    Gauge: jest.fn(() => mockGauge),
    collectDefaultMetrics: jest.fn(),
  };
});

const metrics = require('../src/metrics');

describe('Metrics Module', () => {
  describe('recordUpload', () => {
    it('should record upload status', () => {
      expect(() => metrics.recordUpload('success')).not.toThrow();
      expect(() => metrics.recordUpload('failed')).not.toThrow();
    });
  });

  describe('startUploadTimer', () => {
    it('should return a function to end timing', () => {
      const endTimer = metrics.startUploadTimer();
      expect(typeof endTimer).toBe('function');
      expect(() => endTimer()).not.toThrow();
    });
  });

  describe('setLoginStatus', () => {
    it('should set login status gauge', () => {
      expect(() => metrics.setLoginStatus(true)).not.toThrow();
      expect(() => metrics.setLoginStatus(false)).not.toThrow();
    });
  });

  describe('setPendingUploads', () => {
    it('should set pending uploads gauge', () => {
      expect(() => metrics.setPendingUploads(5)).not.toThrow();
    });
  });

  describe('setFailedUploads', () => {
    it('should set failed uploads gauge', () => {
      expect(() => metrics.setFailedUploads(2)).not.toThrow();
    });
  });

  describe('metricsMiddleware', () => {
    it('should be a function', () => {
      expect(typeof metrics.metricsMiddleware).toBe('function');
    });

    it('should call next()', () => {
      const req = { method: 'GET', path: '/test' };
      const res = { on: jest.fn() };
      const next = jest.fn();

      metrics.metricsMiddleware(req, res, next);
      expect(next).toHaveBeenCalled();
    });
  });

  describe('getMetrics endpoint', () => {
    it('should return metrics', async () => {
      const app = express();
      app.get('/metrics', metrics.getMetrics);

      const response = await request(app).get('/metrics');

      expect(response.status).toBe(200);
      expect(response.text).toContain('test_metric');
    });
  });
});

describe('Metrics Integration', () => {
  it('should track HTTP request metrics', () => {
    const req = {
      method: 'POST',
      path: '/upload',
      route: { path: '/upload' },
    };
    const res = {
      on: jest.fn((event, callback) => {
        if (event === 'finish') {
          res.statusCode = 200;
          callback();
        }
      }),
      statusCode: 200,
    };
    const next = jest.fn();

    metrics.metricsMiddleware(req, res, next);

    expect(next).toHaveBeenCalled();
  });
});
