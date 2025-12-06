#!/usr/bin/env python3
"""
Migration script to add auto-indexing columns to events table
"""
import sqlite3
import os

DATABASE = os.getenv('DATABASE', 'face_recognition.db')

def run_migration():
    """Add auto_index_enabled and last_auto_index_at columns"""
    print("Starting auto-index migration...")

    if not os.path.exists(DATABASE):
        print(f"❌ Database file '{DATABASE}' not found!")
        return False

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(events)")
        columns = [col[1] for col in cursor.fetchall()]

        # Add auto_index_enabled if not exists
        if 'auto_index_enabled' not in columns:
            print("Adding auto_index_enabled column...")
            cursor.execute('''
                ALTER TABLE events
                ADD COLUMN auto_index_enabled INTEGER DEFAULT 0
            ''')
            print("✅ Added auto_index_enabled column")
        else:
            print("ℹ️  auto_index_enabled column already exists")

        # Add last_auto_index_at if not exists
        if 'last_auto_index_at' not in columns:
            print("Adding last_auto_index_at column...")
            cursor.execute('''
                ALTER TABLE events
                ADD COLUMN last_auto_index_at TIMESTAMP
            ''')
            print("✅ Added last_auto_index_at column")
        else:
            print("ℹ️  last_auto_index_at column already exists")

        conn.commit()
        print("\n✅ Migration completed successfully!")
        return True

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        conn.rollback()
        return False

    finally:
        conn.close()

if __name__ == '__main__':
    run_migration()
