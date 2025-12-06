#!/usr/bin/env python3
"""
Migration script to add performance indexes to existing database
Run this to improve search performance
"""

import sqlite3
import os
import sys

DATABASE = 'database.db'

def migrate_database():
    """Add performance indexes if they don't exist"""

    if not os.path.exists(DATABASE):
        print(f"❌ Database file '{DATABASE}' not found.")
        return False

    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        # Check existing indexes
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        existing_indexes = {row[0] for row in cursor.fetchall()}

        print(f"📊 Existing indexes: {existing_indexes}")

        # Add composite index for event_id + indexed_at if not exists
        if 'idx_faces_event_indexed' not in existing_indexes:
            print("🔧 Adding composite index idx_faces_event_indexed...")
            cursor.execute("""
                CREATE INDEX idx_faces_event_indexed ON faces(event_id, indexed_at)
            """)
            print("   ✅ Created idx_faces_event_indexed")
        else:
            print("   ✅ idx_faces_event_indexed already exists")

        conn.commit()
        conn.close()

        print("\n✅ Migration completed successfully!")
        print("   Your database is now optimized for faster searches!")
        return True

    except sqlite3.Error as e:
        print(f"❌ Migration failed: {e}")
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("Database Migration: Performance Indexes")
    print("=" * 60)

    success = migrate_database()

    if success:
        print("\n🚀 Performance improvements:")
        print("   - Faster search queries with vectorized comparison")
        print("   - In-memory cache for repeated searches")
        print("   - Optimized database indexes")
        sys.exit(0)
    else:
        print("\n⚠️  Migration failed. Please check the error above.")
        sys.exit(1)
