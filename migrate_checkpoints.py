#!/usr/bin/env python3
"""
Migration script to add indexing_checkpoints table to existing database
Run this script to update your database schema without losing existing data
"""

import sqlite3
import os
import sys

DATABASE = 'database.db'

def migrate_database():
    """Add indexing_checkpoints table if it doesn't exist"""

    if not os.path.exists(DATABASE):
        print(f"❌ Database file '{DATABASE}' not found.")
        print("   Run 'flask --app app init-db' first to create the database.")
        return False

    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        # Check if table already exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='indexing_checkpoints'
        """)

        if cursor.fetchone():
            print("✅ indexing_checkpoints table already exists. No migration needed.")
            conn.close()
            return True

        print("📦 Creating indexing_checkpoints table...")

        # Create the table
        cursor.execute("""
            CREATE TABLE indexing_checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                photo_id TEXT NOT NULL,
                photo_name TEXT NOT NULL,
                faces_found INTEGER DEFAULT 0,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (event_id) REFERENCES events (id) ON DELETE CASCADE
            )
        """)

        # Create indexes
        cursor.execute("""
            CREATE INDEX idx_checkpoints_event ON indexing_checkpoints(event_id)
        """)

        cursor.execute("""
            CREATE INDEX idx_checkpoints_photo ON indexing_checkpoints(event_id, photo_id)
        """)

        conn.commit()
        conn.close()

        print("✅ Migration completed successfully!")
        print("   indexing_checkpoints table created with indexes.")
        return True

    except sqlite3.Error as e:
        print(f"❌ Migration failed: {e}")
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("Database Migration: Add Indexing Checkpoints")
    print("=" * 60)

    success = migrate_database()

    if success:
        print("\n✨ Your database is now ready for resume functionality!")
        sys.exit(0)
    else:
        print("\n⚠️  Migration failed. Please check the error above.")
        sys.exit(1)
