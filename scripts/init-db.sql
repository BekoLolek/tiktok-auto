-- TikTok Auto Database Initialization Script
-- This script is automatically run when the PostgreSQL container starts

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Stories: Raw Reddit posts
CREATE TABLE IF NOT EXISTS stories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reddit_id VARCHAR(20) UNIQUE NOT NULL,
    subreddit VARCHAR(100) NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    author VARCHAR(100),
    score INTEGER,
    url TEXT,
    char_count INTEGER NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    error_message TEXT,
    rejection_reason TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Scripts: Processed scripts (can be multiple parts per story)
CREATE TABLE IF NOT EXISTS scripts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_id UUID REFERENCES stories(id) ON DELETE CASCADE,
    part_number INTEGER NOT NULL,
    total_parts INTEGER NOT NULL,
    hook TEXT,
    content TEXT NOT NULL,
    cta TEXT,
    char_count INTEGER NOT NULL,
    voice_gender VARCHAR(10),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Audio: Generated narration files
CREATE TABLE IF NOT EXISTS audio (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    script_id UUID REFERENCES scripts(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    duration_seconds FLOAT,
    voice_model VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Videos: Rendered video files
CREATE TABLE IF NOT EXISTS videos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    audio_id UUID REFERENCES audio(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    duration_seconds FLOAT,
    resolution VARCHAR(20),
    background_video TEXT,
    has_captions BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Uploads: Publishing status
CREATE TABLE IF NOT EXISTS uploads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id UUID REFERENCES videos(id) ON DELETE CASCADE,
    platform VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    platform_video_id TEXT,
    platform_url TEXT,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    uploaded_at TIMESTAMP
);

-- Batches: Group multi-part uploads
CREATE TABLE IF NOT EXISTS batches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_id UUID REFERENCES stories(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL,
    total_parts INTEGER NOT NULL,
    completed_parts INTEGER DEFAULT 0,
    failed_parts TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Pipeline runs: Track pipeline executions
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_id UUID REFERENCES stories(id),
    batch_id UUID REFERENCES batches(id),
    status VARCHAR(20) NOT NULL,
    current_step VARCHAR(50),
    started_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    error_message TEXT
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_stories_status ON stories(status);
CREATE INDEX IF NOT EXISTS idx_stories_subreddit ON stories(subreddit);
CREATE INDEX IF NOT EXISTS idx_stories_created_at ON stories(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_scripts_story_id ON scripts(story_id);
CREATE INDEX IF NOT EXISTS idx_audio_script_id ON audio(script_id);
CREATE INDEX IF NOT EXISTS idx_videos_audio_id ON videos(audio_id);
CREATE INDEX IF NOT EXISTS idx_uploads_status ON uploads(status);
CREATE INDEX IF NOT EXISTS idx_uploads_video_id ON uploads(video_id);
CREATE INDEX IF NOT EXISTS idx_batches_story_id ON batches(story_id);
CREATE INDEX IF NOT EXISTS idx_batches_status ON batches(status);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status ON pipeline_runs(status);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_story_id ON pipeline_runs(story_id);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger for stories updated_at
DROP TRIGGER IF EXISTS update_stories_updated_at ON stories;
CREATE TRIGGER update_stories_updated_at
    BEFORE UPDATE ON stories
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Insert some test data for development (optional)
-- Uncomment if you want sample data

-- INSERT INTO stories (reddit_id, subreddit, title, content, author, score, char_count, status)
-- VALUES
--     ('test001', 'scifi', 'Test Story 1', 'This is a test story content for development.', 'testuser', 100, 50, 'pending'),
--     ('test002', 'fantasy', 'Test Story 2', 'Another test story with more content for testing the pipeline.', 'anotheruser', 250, 75, 'pending');

-- Grant permissions (if needed for specific users)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO tiktok_auto;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO tiktok_auto;
