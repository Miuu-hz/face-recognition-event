#!/usr/bin/env python3
"""
Migration script to migrate data from SQLite to PostgreSQL
Run this to move your existing data to PostgreSQL
"""

import sqlite3
import psycopg2
import psycopg2.extras
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Database configurations
SQLITE_DB = os.getenv('DATABASE_PATH', 'database.db')
POSTGRES_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', '5432')),
    'database': os.getenv('POSTGRES_DB', 'face_recognition'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', ''),
}

def migrate_database():
    """Migrate data from SQLite to PostgreSQL"""

    if not os.path.exists(SQLITE_DB):
        print(f"❌ SQLite database '{SQLITE_DB}' not found.")
        return False

    try:
        # Connect to SQLite
        print(f"📂 Connecting to SQLite database: {SQLITE_DB}")
        sqlite_conn = sqlite3.connect(SQLITE_DB)
        sqlite_conn.row_factory = sqlite3.Row
        sqlite_cursor = sqlite_conn.cursor()

        # Connect to PostgreSQL
        print(f"📊 Connecting to PostgreSQL database: {POSTGRES_CONFIG['database']}")
        pg_conn = psycopg2.connect(**POSTGRES_CONFIG)
        pg_cursor = pg_conn.cursor()

        # Migrate events table
        print("\n🔄 Migrating events table...")
        sqlite_cursor.execute("SELECT * FROM events")
        events = sqlite_cursor.fetchall()

        for event in events:
            pg_cursor.execute("""
                INSERT INTO events (id, name, link, qr_path, drive_folder_id, drive_page_token,
                                   indexing_status, indexed_photos, total_faces, task_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    link = EXCLUDED.link,
                    indexing_status = EXCLUDED.indexing_status,
                    indexed_photos = EXCLUDED.indexed_photos,
                    total_faces = EXCLUDED.total_faces
            """, (
                event['id'], event['name'], event['link'], event['qr_path'],
                event['drive_folder_id'], event.get('drive_page_token'),
                event['indexing_status'], event['indexed_photos'], event['total_faces'],
                event['task_id'], event['created_at']
            ))
        pg_conn.commit()
        print(f"   ✅ Migrated {len(events)} events")

        # Migrate faces table
        print("\n🔄 Migrating faces table...")
        sqlite_cursor.execute("SELECT * FROM faces")
        faces = sqlite_cursor.fetchall()

        batch_size = 1000
        for i in range(0, len(faces), batch_size):
            batch = faces[i:i+batch_size]
            for face in batch:
                pg_cursor.execute("""
                    INSERT INTO faces (event_id, photo_id, photo_name, face_encoding, face_location, indexed_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    face['event_id'], face['photo_id'], face['photo_name'],
                    face['face_encoding'], face['face_location'], face['indexed_at']
                ))
            pg_conn.commit()
            print(f"   ✅ Migrated {min(i+batch_size, len(faces))}/{len(faces)} faces")

        # Migrate checkpoints table
        print("\n🔄 Migrating indexing_checkpoints table...")
        sqlite_cursor.execute("SELECT * FROM indexing_checkpoints")
        checkpoints = sqlite_cursor.fetchall()

        for checkpoint in checkpoints:
            pg_cursor.execute("""
                INSERT INTO indexing_checkpoints (event_id, photo_id, photo_name, faces_found, processed_at)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                checkpoint['event_id'], checkpoint['photo_id'], checkpoint['photo_name'],
                checkpoint['faces_found'], checkpoint['processed_at']
            ))
        pg_conn.commit()
        print(f"   ✅ Migrated {len(checkpoints)} checkpoints")

        # Close connections
        sqlite_conn.close()
        pg_cursor.close()
        pg_conn.close()

        print("\n✅ Migration completed successfully!")
        print(f"   📊 Total migrated:")
        print(f"      - Events: {len(events)}")
        print(f"      - Faces: {len(faces)}")
        print(f"      - Checkpoints: {len(checkpoints)}")
        return True

    except psycopg2.Error as e:
        print(f"❌ PostgreSQL error: {e}")
        return False
    except sqlite3.Error as e:
        print(f"❌ SQLite error: {e}")
        return False
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("SQLite to PostgreSQL Migration")
    print("=" * 60)
    print()
    print("⚠️  WARNING: Make sure PostgreSQL database exists and schema is initialized!")
    print("   Run this first: psql -U postgres -d face_recognition -f schema_postgresql.sql")
    print()

    response = input("Continue with migration? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print("Migration cancelled.")
        sys.exit(0)

    success = migrate_database()

    if success:
        print("\n✨ Next steps:")
        print("   1. Update .env: Set DATABASE_TYPE=postgresql")
        print("   2. Restart your application")
        print("   3. Verify everything works correctly")
        print("   4. Optionally backup and remove database.db")
        sys.exit(0)
    else:
        print("\n⚠️  Migration failed. Please check the errors above.")
        sys.exit(1)
