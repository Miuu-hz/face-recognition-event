"""
Database Migration Script - Add task_id column to events table

This script adds the task_id column that was introduced in Phase 1
to existing databases created before Phase 1.

Usage:
    python migrate_db.py
"""

import sqlite3
import os

DATABASE = 'database.db'

def migrate_database():
    """Add task_id column to events table if it doesn't exist"""

    if not os.path.exists(DATABASE):
        print(f"❌ Database file '{DATABASE}' not found!")
        print("   Run 'flask --app app init-db' to create a new database.")
        return False

    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        # Check if task_id column already exists
        cursor.execute("PRAGMA table_info(events)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'task_id' in columns:
            print("✅ Database already has task_id column - no migration needed!")
            conn.close()
            return True

        print("🔧 Migrating database: Adding task_id column to events table...")

        # Add task_id column
        cursor.execute("ALTER TABLE events ADD COLUMN task_id TEXT")
        conn.commit()

        print("✅ Migration completed successfully!")
        print("   Added column: task_id (TEXT)")

        conn.close()
        return True

    except sqlite3.Error as e:
        print(f"❌ Migration failed: {e}")
        return False

if __name__ == '__main__':
    print("="*60)
    print("Database Migration: Add task_id to events table")
    print("="*60)

    success = migrate_database()

    if success:
        print("\n✅ Database is now ready for Phase 1 features!")
    else:
        print("\n❌ Migration failed. Consider deleting database.db and")
        print("   running 'flask --app app init-db' to create a fresh database.")

    print("="*60)
