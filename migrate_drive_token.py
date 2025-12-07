#!/usr/bin/env python3
"""
Migration script to add drive_page_token column to events table
Run this to upgrade existing databases
"""

import sqlite3
import os
import sys

DATABASE = 'database.db'

def migrate_database():
    """Add drive_page_token column if it doesn't exist"""

    if not os.path.exists(DATABASE):
        print(f"❌ Database file '{DATABASE}' not found.")
        return False

    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        # Check if column already exists
        cursor.execute("PRAGMA table_info(events)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'drive_page_token' in columns:
            print("✅ drive_page_token column already exists. No migration needed.")
            conn.close()
            return True

        print("📦 Adding drive_page_token column to events table...")

        # Add the column
        cursor.execute("""
            ALTER TABLE events ADD COLUMN drive_page_token TEXT
        """)

        conn.commit()
        conn.close()

        print("✅ Migration completed successfully!")
        print("   drive_page_token column added to events table.")
        return True

    except sqlite3.Error as e:
        print(f"❌ Migration failed: {e}")
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("Database Migration: Add Drive Page Token")
    print("=" * 60)

    success = migrate_database()

    if success:
        print("\n✨ Your database now supports Google Drive Changes API!")
        print("   This will make new photo detection much faster!")
        sys.exit(0)
    else:
        print("\n⚠️  Migration failed. Please check the error above.")
        sys.exit(1)
