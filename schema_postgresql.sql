-- PostgreSQL Schema for Face Recognition Event System

-- Drop existing tables if they exist
DROP TABLE IF EXISTS indexing_checkpoints CASCADE;
DROP TABLE IF EXISTS faces CASCADE;
DROP TABLE IF EXISTS events CASCADE;

-- Events table
CREATE TABLE events (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    link TEXT NOT NULL,
    qr_path TEXT NOT NULL,
    drive_folder_id TEXT,
    drive_page_token TEXT,
    indexing_status TEXT DEFAULT 'Not Started',
    indexed_photos INTEGER DEFAULT 0,
    total_faces INTEGER DEFAULT 0,
    task_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Faces table with face encodings
CREATE TABLE faces (
    id SERIAL PRIMARY KEY,
    event_id TEXT NOT NULL,
    photo_id TEXT NOT NULL,
    photo_name TEXT,
    face_encoding BYTEA NOT NULL,
    face_location TEXT,
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (event_id) REFERENCES events (id) ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX idx_faces_event ON faces(event_id);
CREATE INDEX idx_faces_photo ON faces(photo_id);
CREATE INDEX idx_faces_event_indexed ON faces(event_id, indexed_at);  -- Composite index for ordered queries

-- Indexing checkpoints for resume functionality
CREATE TABLE indexing_checkpoints (
    id SERIAL PRIMARY KEY,
    event_id TEXT NOT NULL,
    photo_id TEXT NOT NULL,
    photo_name TEXT NOT NULL,
    faces_found INTEGER DEFAULT 0,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (event_id) REFERENCES events (id) ON DELETE CASCADE
);

-- Index for checkpoint queries
CREATE INDEX idx_checkpoints_event ON indexing_checkpoints(event_id);
CREATE INDEX idx_checkpoints_photo ON indexing_checkpoints(event_id, photo_id);
