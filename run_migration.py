#!/usr/bin/env python3
"""
Run database migration for Phase 3: Auto-sync with Drive Changes API
"""
import sqlite3
import os

DATABASE = 'database.db'
MIGRATION_FILE = 'migration_phase3_auto_sync.sql'

def run_migration():
    """Run the migration SQL file"""
    if not os.path.exists(DATABASE):
        print(f"❌ Database file '{DATABASE}' not found!")
        print("Please run 'flask --app app init-db' first to initialize the database.")
        return False

    if not os.path.exists(MIGRATION_FILE):
        print(f"❌ Migration file '{MIGRATION_FILE}' not found!")
        return False

    try:
        # Read migration SQL
        with open(MIGRATION_FILE, 'r') as f:
            migration_sql = f.read()

        # Connect to database
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        # Execute migration
        print(f"Running migration from {MIGRATION_FILE}...")
        cursor.executescript(migration_sql)
        conn.commit()

        print("✅ Migration completed successfully!")

        # Verify new columns exist
        cursor.execute("PRAGMA table_info(events)")
        columns = [row[1] for row in cursor.fetchall()]

        new_columns = ['drive_start_page_token', 'auto_sync_enabled', 'last_sync_at', 'sync_interval_minutes']
        missing = [col for col in new_columns if col not in columns]

        if missing:
            print(f"⚠️  Warning: Some columns were not added: {missing}")
        else:
            print(f"✅ All new columns added to events table: {', '.join(new_columns)}")

        # Check synced_photos table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='synced_photos'")
        if cursor.fetchone():
            print("✅ synced_photos table created successfully")
        else:
            print("⚠️  Warning: synced_photos table was not created")

        conn.close()
        return True

    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("ℹ️  Migration already applied (columns exist)")
            return True
        else:
            print(f"❌ Error running migration: {e}")
            return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == '__main__':
    success = run_migration()
    exit(0 if success else 1)
