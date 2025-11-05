-- Drop existing tables if they exist
DROP TABLE IF EXISTS tasks;
DROP TABLE IF EXISTS faces;
DROP TABLE IF EXISTS events;

-- Events table
CREATE TABLE events (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    link TEXT NOT NULL,
    qr_path TEXT NOT NULL,
    drive_folder_id TEXT,
    indexing_status TEXT DEFAULT 'Not Started',
    indexed_photos INTEGER DEFAULT 0,
    total_faces INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Faces table with face encodings
CREATE TABLE faces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    photo_id TEXT NOT NULL,
    photo_name TEXT,
    face_encoding BLOB NOT NULL,
    face_location TEXT,
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (event_id) REFERENCES events (id) ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX idx_faces_event ON faces(event_id);
CREATE INDEX idx_faces_photo ON faces(photo_id);

-- Background Tasks table for async job tracking
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    task_type TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    progress INTEGER DEFAULT 0,
    total INTEGER DEFAULT 0,
    current_item TEXT,
    result TEXT,
    error TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (event_id) REFERENCES events (id) ON DELETE CASCADE
);

-- Indexes for task tracking
CREATE INDEX idx_tasks_event ON tasks(event_id);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_created ON tasks(created_at);