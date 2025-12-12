"""
โมดูลสำหรับ Face Database Operations
จัดการการบันทึกและดึงข้อมูล face encodings จากฐานข้อมูล

ฟีเจอร์หลัก:
- บันทึก face encodings ลง database
- ดึง faces ตาม event_id
- Checkpoint management สำหรับ resume functionality
- รองรับทั้ง SQLite และ PostgreSQL
"""

import json
import logging
import numpy as np
from datetime import datetime

logger = logging.getLogger('face_recognition_app')


class FaceDatabaseError(Exception):
    """Exception สำหรับ error ในการทำงานกับฐานข้อมูล"""
    pass


def save_face_to_db(db_conn, event_id, photo_id, photo_name, encoding, location):
    """บันทึก face encoding ลงฐานข้อมูล

    Args:
        db_conn: database connection
        event_id (str): ID ของ event
        photo_id (str): Google Drive photo ID
        photo_name (str): ชื่อไฟล์ภาพ
        encoding (np.ndarray): 128-d face encoding
        location (dict): {'top': int, 'right': int, 'bottom': int, 'left': int}

    Raises:
        FaceDatabaseError: ถ้าไม่สามารถบันทึกได้
    """
    try:
        # แปลง numpy array → binary blob
        encoding_blob = encoding.tobytes()
        location_json = json.dumps(location)

        db_conn.execute(
            'INSERT INTO faces (event_id, photo_id, photo_name, face_encoding, face_location) VALUES (?, ?, ?, ?, ?)',
            (event_id, photo_id, photo_name, encoding_blob, location_json)
        )

        logger.debug(f"บันทึก face จาก {photo_name} ลง DB สำเร็จ")

    except Exception as e:
        error_msg = f"ไม่สามารถบันทึก face จาก {photo_name}: {e}"
        logger.error(error_msg)
        raise FaceDatabaseError(error_msg)


def save_faces_batch(db_conn, event_id, photo_id, photo_name, faces):
    """บันทึกหลาย faces จากภาพเดียวพร้อมกัน

    Args:
        db_conn: database connection
        event_id (str): ID ของ event
        photo_id (str): Google Drive photo ID
        photo_name (str): ชื่อไฟล์ภาพ
        faces (list): รายการ dict ที่มี 'encoding' และ 'location'

    Returns:
        int: จำนวน faces ที่บันทึกสำเร็จ

    Raises:
        FaceDatabaseError: ถ้าไม่สามารถบันทึกได้
    """
    if not faces:
        return 0

    try:
        count = 0
        for face_data in faces:
            save_face_to_db(
                db_conn,
                event_id,
                photo_id,
                photo_name,
                face_data['encoding'],
                face_data['location']
            )
            count += 1

        logger.debug(f"บันทึก {count} faces จาก {photo_name}")
        return count

    except FaceDatabaseError:
        raise
    except Exception as e:
        error_msg = f"ไม่สามารถบันทึก faces จาก {photo_name}: {e}"
        logger.error(error_msg)
        raise FaceDatabaseError(error_msg)


def get_faces_by_event(db_conn, event_id):
    """ดึงข้อมูล faces ทั้งหมดของ event

    Args:
        db_conn: database connection
        event_id (str): ID ของ event

    Returns:
        list: รายการ dict ที่มี photo_id, photo_name, encoding, location

    Raises:
        FaceDatabaseError: ถ้าไม่สามารถดึงข้อมูลได้
    """
    try:
        cursor = db_conn.execute(
            'SELECT photo_id, photo_name, face_encoding, face_location FROM faces WHERE event_id = ? ORDER BY indexed_at',
            (event_id,)
        )
        rows = cursor.fetchall()

        faces = []
        for row in rows:
            # แปลง binary blob → numpy array
            encoding = np.frombuffer(row['face_encoding'], dtype=np.float64)
            location = json.loads(row['face_location'])

            faces.append({
                'photo_id': row['photo_id'],
                'photo_name': row['photo_name'],
                'encoding': encoding,
                'location': location
            })

        logger.debug(f"ดึง {len(faces)} faces จาก event {event_id}")
        return faces

    except Exception as e:
        error_msg = f"ไม่สามารถดึง faces จาก event {event_id}: {e}"
        logger.error(error_msg)
        raise FaceDatabaseError(error_msg)


def get_indexed_photo_ids(db_conn, event_id):
    """ดึง photo IDs ที่ index แล้วทั้งหมด

    Args:
        db_conn: database connection
        event_id (str): ID ของ event

    Returns:
        set: เซตของ photo IDs ที่ index แล้ว
    """
    try:
        cursor = db_conn.execute(
            'SELECT DISTINCT photo_id FROM faces WHERE event_id = ?',
            (event_id,)
        )
        rows = cursor.fetchall()
        photo_ids = {row['photo_id'] for row in rows}

        logger.debug(f"พบ {len(photo_ids)} ภาพที่ index แล้วใน event {event_id}")
        return photo_ids

    except Exception as e:
        logger.error(f"ไม่สามารถดึง indexed photo IDs: {e}")
        return set()


def delete_faces_by_event(db_conn, event_id):
    """ลบ faces ทั้งหมดของ event (สำหรับการ re-index)

    Args:
        db_conn: database connection
        event_id (str): ID ของ event

    Returns:
        int: จำนวน faces ที่ลบ
    """
    try:
        cursor = db_conn.execute(
            'SELECT COUNT(*) as count FROM faces WHERE event_id = ?',
            (event_id,)
        )
        count = cursor.fetchone()['count']

        db_conn.execute('DELETE FROM faces WHERE event_id = ?', (event_id,))
        db_conn.commit()

        logger.info(f"ลบ {count} faces จาก event {event_id}")
        return count

    except Exception as e:
        logger.error(f"ไม่สามารถลบ faces: {e}")
        raise FaceDatabaseError(f"Failed to delete faces: {e}")


def get_face_count_by_event(db_conn, event_id):
    """นับจำนวน faces ในฐานข้อมูล

    Args:
        db_conn: database connection
        event_id (str): ID ของ event

    Returns:
        int: จำนวน faces
    """
    try:
        cursor = db_conn.execute(
            'SELECT COUNT(*) as count FROM faces WHERE event_id = ?',
            (event_id,)
        )
        count = cursor.fetchone()['count']
        return count

    except Exception as e:
        logger.error(f"ไม่สามารถนับ faces: {e}")
        return 0


# --- Checkpoint Management ---

def ensure_checkpoint_table(db_conn):
    """สร้างตาราง indexing_checkpoints ถ้ายังไม่มี (auto-migration)

    Args:
        db_conn: database connection

    Returns:
        bool: True ถ้าสำเร็จ
    """
    try:
        # ตรวจสอบว่ามีตารางหรือไม่
        cursor = db_conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='indexing_checkpoints'
        """)

        if not cursor.fetchone():
            logger.info("สร้างตาราง indexing_checkpoints (auto-migration)...")

            db_conn.execute("""
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

            db_conn.execute("""
                CREATE INDEX idx_checkpoints_event ON indexing_checkpoints(event_id)
            """)

            db_conn.execute("""
                CREATE INDEX idx_checkpoints_photo ON indexing_checkpoints(event_id, photo_id)
            """)

            db_conn.commit()
            logger.info("✅ สร้างตาราง indexing_checkpoints สำเร็จ")

        return True

    except Exception as e:
        logger.error(f"❌ ไม่สามารถสร้างตาราง checkpoint: {e}")
        return False


def get_checkpoints(db_conn, event_id):
    """ดึงข้อมูล checkpoints ของ event

    Args:
        db_conn: database connection
        event_id (str): ID ของ event

    Returns:
        dict: {photo_id: {'name': str, 'faces': int}, ...}
    """
    try:
        if not ensure_checkpoint_table(db_conn):
            return {}

        cursor = db_conn.execute(
            'SELECT photo_id, photo_name, faces_found FROM indexing_checkpoints WHERE event_id = ?',
            (event_id,)
        )
        rows = cursor.fetchall()

        checkpoints = {
            row['photo_id']: {
                'name': row['photo_name'],
                'faces': row['faces_found']
            }
            for row in rows
        }

        logger.debug(f"พบ {len(checkpoints)} checkpoints สำหรับ event {event_id}")
        return checkpoints

    except Exception as e:
        logger.warning(f"ไม่สามารถดึง checkpoints: {e}")
        return {}


def save_checkpoint(db_conn, event_id, photo_id, photo_name, faces_found):
    """บันทึก checkpoint หลังประมวลผลภาพ

    Args:
        db_conn: database connection
        event_id (str): ID ของ event
        photo_id (str): photo ID
        photo_name (str): ชื่อไฟล์
        faces_found (int): จำนวน faces ที่พบ
    """
    try:
        if not ensure_checkpoint_table(db_conn):
            return

        db_conn.execute(
            'INSERT INTO indexing_checkpoints (event_id, photo_id, photo_name, faces_found) VALUES (?, ?, ?, ?)',
            (event_id, photo_id, photo_name, faces_found)
        )
        db_conn.commit()

        logger.debug(f"บันทึก checkpoint: {photo_name} ({faces_found} faces)")

    except Exception as e:
        logger.warning(f"ไม่สามารถบันทึก checkpoint สำหรับ {photo_name}: {e}")


def clear_checkpoints(db_conn, event_id):
    """ลบ checkpoints ทั้งหมดของ event (เมื่อเสร็จสมบูรณ์)

    Args:
        db_conn: database connection
        event_id (str): ID ของ event
    """
    try:
        if not ensure_checkpoint_table(db_conn):
            return

        db_conn.execute('DELETE FROM indexing_checkpoints WHERE event_id = ?', (event_id,))
        db_conn.commit()

        logger.info(f"ลบ checkpoints สำหรับ event {event_id}")

    except Exception as e:
        logger.warning(f"ไม่สามารถลบ checkpoints: {e}")


def count_checkpoints(db_conn, event_id):
    """นับจำนวน checkpoints

    Args:
        db_conn: database connection
        event_id (str): ID ของ event

    Returns:
        int: จำนวน checkpoints
    """
    try:
        if not ensure_checkpoint_table(db_conn):
            return 0

        cursor = db_conn.execute(
            'SELECT COUNT(*) as count FROM indexing_checkpoints WHERE event_id = ?',
            (event_id,)
        )
        return cursor.fetchone()['count']

    except Exception as e:
        logger.warning(f"ไม่สามารถนับ checkpoints: {e}")
        return 0


def get_checkpoint_photo_ids(db_conn, event_id):
    """ดึง photo IDs จาก checkpoints

    Args:
        db_conn: database connection
        event_id (str): ID ของ event

    Returns:
        set: เซตของ photo IDs ที่มี checkpoint
    """
    try:
        cursor = db_conn.execute(
            'SELECT DISTINCT photo_id FROM indexing_checkpoints WHERE event_id = ?',
            (event_id,)
        )
        rows = cursor.fetchall()
        return {row['photo_id'] for row in rows}

    except Exception as e:
        logger.warning(f"ไม่สามารถดึง checkpoint photo IDs: {e}")
        return set()


# Export public API
__all__ = [
    'save_face_to_db',
    'save_faces_batch',
    'get_faces_by_event',
    'get_indexed_photo_ids',
    'delete_faces_by_event',
    'get_face_count_by_event',
    'ensure_checkpoint_table',
    'get_checkpoints',
    'save_checkpoint',
    'clear_checkpoints',
    'count_checkpoints',
    'get_checkpoint_photo_ids',
    'FaceDatabaseError',
]
