-- Migration for Phase 3: Auto-sync with Drive Changes API
-- Add fields for tracking Google Drive changes and auto-sync

-- Add columns to events table
ALTER TABLE events ADD COLUMN drive_start_page_token TEXT;
ALTER TABLE events ADD COLUMN auto_sync_enabled INTEGER DEFAULT 0;
ALTER TABLE events ADD COLUMN last_sync_at TIMESTAMP;
ALTER TABLE events ADD COLUMN sync_interval_minutes INTEGER DEFAULT 2;

-- Create table for tracking synced photos (to avoid duplicates)
CREATE TABLE IF NOT EXISTS synced_photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    photo_id TEXT NOT NULL,
    photo_name TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (event_id) REFERENCES events (id) ON DELETE CASCADE,
    UNIQUE(event_id, photo_id)
);

CREATE INDEX idx_synced_photos_event ON synced_photos(event_id);
CREATE INDEX idx_synced_photos_photo ON synced_photos(photo_id);
