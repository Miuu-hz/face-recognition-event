"""
โมดูลสำหรับ Face Indexing Service
จัดการการ index ภาพจาก Google Drive ทั้งแบบ Full และ Incremental

ฟีเจอร์หลัก:
- Full indexing: ประมวลผลทุกภาพใน folder
- Incremental indexing: ประมวลผลเฉพาะภาพใหม่ (ใช้ Drive Changes API)
- Resume functionality: ทำงานต่อจากจุดที่หยุด
- Progress tracking: อัพเดท progress แบบ real-time
- Error handling: จัดการ errors และ retry
"""

import os
import logging
import tempfile
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from . import face_encoder, face_database

logger = logging.getLogger('face_recognition_app')


class IndexingError(Exception):
    """Exception สำหรับ error ในการ indexing"""
    pass


def download_image_from_drive(drive_service, photo_id, max_retries=3):
    """ดาวน์โหลดภาพจาก Google Drive ไปยัง temp file

    Args:
        drive_service: Google Drive service instance
        photo_id (str): ID ของภาพ
        max_retries (int): จำนวนครั้งที่ retry

    Returns:
        str: path ของ temp file หรือ None ถ้าล้มเหลว

    Raises:
        IndexingError: ถ้า download ล้มเหลวหลังจาก retry ครบแล้ว
    """
    from googleapiclient.http import MediaIoBaseDownload
    import io
    import time

    for attempt in range(max_retries):
        try:
            request = drive_service.files().get_media(fileId=photo_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)

            done = False
            while not done:
                status, done = downloader.next_chunk()

            # บันทึกลง temp file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
            temp_file.write(fh.getvalue())
            temp_file.close()

            logger.debug(f"ดาวน์โหลด {photo_id} สำเร็จ")
            return temp_file.name

        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"ดาวน์โหลด {photo_id} ล้มเหลว (ครั้งที่ {attempt + 1}/{max_retries}): {e}")
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                logger.error(f"ดาวน์โหลด {photo_id} ล้มเหลวหลัง {max_retries} ครั้ง: {e}")
                raise IndexingError(f"Failed to download image {photo_id}: {e}")

    return None


def index_single_photo(drive_service, db_conn, event_id, photo_id, photo_name, config):
    """Index ภาพเดียว

    Args:
        drive_service: Google Drive service
        db_conn: database connection
        event_id (str): ID ของ event
        photo_id (str): Google Drive photo ID
        photo_name (str): ชื่อไฟล์
        config (dict): configuration {'model': str, 'num_jitters': int}

    Returns:
        int: จำนวน faces ที่พบ

    Raises:
        IndexingError: ถ้าเกิด error ในการประมวลผล
    """
    temp_path = None

    try:
        # ดาวน์โหลดภาพ
        temp_path = download_image_from_drive(drive_service, photo_id)
        if not temp_path:
            logger.warning(f"ข้าม {photo_name} - ดาวน์โหลดล้มเหลว")
            return 0

        # Extract face encodings
        try:
            faces = face_encoder.extract_face_encodings(
                temp_path,
                model=config.get('model', 'hog'),
                num_jitters=config.get('num_jitters', 1)
            )
        except face_encoder.ImageProcessingError as e:
            logger.warning(f"ข้าม {photo_name} - {e}")
            return 0

        if not faces:
            logger.debug(f"ไม่พบใบหน้าใน {photo_name}")
            return 0

        # บันทึกลง database
        faces_count = face_database.save_faces_batch(
            db_conn,
            event_id,
            photo_id,
            photo_name,
            faces
        )

        logger.debug(f"Index {photo_name} สำเร็จ: พบ {faces_count} ใบหน้า")
        return faces_count

    finally:
        # ลบ temp file
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass


def run_full_indexing(task, event_id, folder_id, credentials_dict, db_conn, config):
    """ทำ Full Indexing สำหรับ event (ประมวลผลทุกภาพ)

    Args:
        task: Task object สำหรับ progress tracking
        event_id (str): ID ของ event
        folder_id (str): Google Drive folder ID
        credentials_dict (dict): Google OAuth credentials
        db_conn: database connection
        config (dict): configuration {'model': str, 'num_jitters': int, 'batch_size': int}

    Raises:
        IndexingError: ถ้าเกิด error ร้ายแรง
    """
    try:
        task.start()
        logger.info(f"เริ่ม Full Indexing สำหรับ event {event_id}")

        # Validate credentials
        required_fields = ['token', 'refresh_token', 'token_uri', 'client_id', 'client_secret']
        missing_fields = [f for f in required_fields if f not in credentials_dict or not credentials_dict[f]]

        if missing_fields:
            error_msg = f"Credentials ไม่ครบ: {', '.join(missing_fields)}"
            logger.error(error_msg)
            task.fail(error_msg)
            db_conn.execute("UPDATE events SET indexing_status = ? WHERE id = ?", ('Failed', event_id))
            db_conn.commit()
            return

        # Build Drive service
        creds = Credentials(**credentials_dict)
        drive_service = build('drive', 'v3', credentials=creds)

        # ตรวจสอบ checkpoints (resume functionality)
        processed_photos = face_database.get_checkpoints(db_conn, event_id)
        resuming = len(processed_photos) > 0

        if resuming:
            logger.info(f"Resume จาก checkpoint: {len(processed_photos)} ภาพทำแล้ว")
            total_faces = sum(p['faces'] for p in processed_photos.values())
            indexed_photos = len(processed_photos)
        else:
            logger.info("เริ่มต้น indexing ใหม่")
            total_faces = 0
            indexed_photos = 0

        # ดึงรายการภาพจาก Google Drive
        query = f"'{folder_id}' in parents and (mimeType='image/jpeg' or mimeType='image/png' or mimeType='image/jpg') and trashed=false"
        results = drive_service.files().list(
            q=query,
            fields="files(id, name)",
            pageSize=100
        ).execute()

        photos = results.get('files', [])
        total_photos = len(photos)

        task.update_progress(indexed_photos, total_photos, None, faces_found=total_faces)
        logger.info(f"พบ {total_photos} ภาพ (ทำแล้ว {indexed_photos}, เหลือ {total_photos - indexed_photos})")

        # ประมวลผลทีละ batch
        batch_size = config.get('batch_size', 20)

        for i in range(0, len(photos), batch_size):
            batch = photos[i:i+batch_size]
            logger.debug(f"ประมวลผล batch {i//batch_size + 1} ({len(batch)} ภาพ)")

            for photo in batch:
                photo_id = photo['id']
                photo_name = photo['name']

                # ข้ามถ้าทำแล้ว (resume)
                if photo_id in processed_photos:
                    logger.debug(f"ข้าม {photo_name} (ทำแล้ว)")
                    continue

                # อัพเดท progress
                task.update_progress(indexed_photos, total_photos, photo_name, faces_found=total_faces)

                # Index ภาพ
                try:
                    faces_found = index_single_photo(
                        drive_service,
                        db_conn,
                        event_id,
                        photo_id,
                        photo_name,
                        config
                    )

                    total_faces += faces_found
                    indexed_photos += 1

                    # บันทึก checkpoint
                    face_database.save_checkpoint(db_conn, event_id, photo_id, photo_name, faces_found)

                    # อัพเดท database progress
                    db_conn.execute(
                        "UPDATE events SET indexed_photos = ?, total_faces = ? WHERE id = ?",
                        (indexed_photos, total_faces, event_id)
                    )
                    db_conn.commit()

                except Exception as e:
                    logger.error(f"Error ในการประมวลผล {photo_name}: {e}")
                    # ทำต่อกับภาพถัดไป

        # อัพเดทสถานะสุดท้าย
        db_conn.execute(
            "UPDATE events SET indexing_status = ?, indexed_photos = ?, total_faces = ? WHERE id = ?",
            ('Completed', indexed_photos, total_faces, event_id)
        )
        db_conn.commit()

        # ลบ checkpoints
        face_database.clear_checkpoints(db_conn, event_id)

        task.complete()
        logger.info(f"Full Indexing เสร็จสิ้น: {indexed_photos} ภาพ, {total_faces} ใบหน้า")

    except HttpError as e:
        error_msg = f"Google Drive API error: {e}"
        logger.error(error_msg)
        task.fail(error_msg)
        db_conn.execute("UPDATE events SET indexing_status = ? WHERE id = ?", ('Failed', event_id))
        db_conn.commit()

    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        logger.error(error_msg, exc_info=True)
        task.fail(error_msg)
        db_conn.execute("UPDATE events SET indexing_status = ? WHERE id = ?", ('Failed', event_id))
        db_conn.commit()


def ensure_drive_token_column(db_conn):
    """สร้างคอลัมน์ drive_page_token ถ้ายังไม่มี

    Args:
        db_conn: database connection

    Returns:
        bool: True ถ้าสำเร็จ
    """
    try:
        cursor = db_conn.execute("PRAGMA table_info(events)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'drive_page_token' not in columns:
            logger.info("เพิ่มคอลัมน์ drive_page_token (auto-migration)...")
            db_conn.execute("ALTER TABLE events ADD COLUMN drive_page_token TEXT")
            db_conn.commit()
            logger.info("✅ เพิ่มคอลัมน์ drive_page_token สำเร็จ")

        return True

    except Exception as e:
        logger.error(f"❌ ไม่สามารถเพิ่มคอลัมน์ drive_page_token: {e}")
        return False


def run_incremental_indexing(task, event_id, folder_id, credentials_dict, db_conn, config):
    """ทำ Incremental Indexing (ประมวลผลเฉพาะภาพใหม่)

    ใช้ Google Drive Changes API เพื่อหาภาพใหม่ที่ถูกเพิ่มเข้ามา
    เร็วกว่า Full Indexing มาก เพราะไม่ต้อง list ทุกไฟล์

    Args:
        task: Task object
        event_id (str): ID ของ event
        folder_id (str): Google Drive folder ID
        credentials_dict (dict): Google OAuth credentials
        db_conn: database connection
        config (dict): configuration

    Raises:
        IndexingError: ถ้าเกิด error ร้ายแรง
    """
    try:
        task.start()
        logger.info(f"เริ่ม Incremental Indexing สำหรับ event {event_id}")

        # Validate credentials
        required_fields = ['token', 'refresh_token', 'token_uri', 'client_id', 'client_secret']
        missing_fields = [f for f in required_fields if f not in credentials_dict or not credentials_dict[f]]

        if missing_fields:
            error_msg = f"Credentials ไม่ครบ: {', '.join(missing_fields)}"
            logger.error(error_msg)
            task.fail(error_msg)
            db_conn.execute("UPDATE events SET indexing_status = ? WHERE id = ?", ('Failed', event_id))
            db_conn.commit()
            return

        # Build Drive service
        creds = Credentials(**credentials_dict)
        drive_service = build('drive', 'v3', credentials=creds)

        # Ensure drive_page_token column exists
        ensure_drive_token_column(db_conn)

        # ดึงข้อมูล event
        event_data = db_conn.execute(
            'SELECT name, drive_page_token FROM events WHERE id = ?',
            (event_id,)
        ).fetchone()

        if not event_data:
            task.fail("ไม่พบ event")
            return

        page_token = event_data['drive_page_token']

        # ดึง photo IDs ที่ index แล้ว
        indexed_ids = face_database.get_indexed_photo_ids(db_conn, event_id)
        checkpoint_ids = face_database.get_checkpoint_photo_ids(db_conn, event_id)
        processed_ids = indexed_ids | checkpoint_ids

        # หาภาพใหม่โดยใช้ Changes API
        new_photos = []

        if not page_token:
            # ครั้งแรก: initialize และ list ทุกไฟล์
            logger.info("Initialize Drive Changes API...")
            response = drive_service.changes().getStartPageToken().execute()
            new_page_token = response.get('startPageToken')

            # List ทุกไฟล์เพื่อหาที่ยัง index
            query = f"'{folder_id}' in parents and (mimeType='image/jpeg' or mimeType='image/png' or mimeType='image/jpg') and trashed=false"
            results = drive_service.files().list(
                q=query,
                fields="files(id, name)",
                pageSize=1000
            ).execute()

            all_photos = results.get('files', [])
            new_photos = [p for p in all_photos if p['id'] not in processed_ids]

            # บันทึก token
            db_conn.execute(
                'UPDATE events SET drive_page_token = ? WHERE id = ?',
                (new_page_token, event_id)
            )
            db_conn.commit()

        else:
            # ใช้ Changes API หาเฉพาะไฟล์ที่เปลี่ยนแปลง
            logger.info("ใช้ Drive Changes API หาภาพใหม่...")
            new_page_token = page_token

            while True:
                try:
                    response = drive_service.changes().list(
                        pageToken=new_page_token,
                        spaces='drive',
                        fields='nextPageToken, newStartPageToken, changes(fileId, file(id, name, mimeType, parents, trashed))',
                        includeRemoved=True
                    ).execute()

                    changes = response.get('changes', [])

                    # กรองเฉพาะภาพในโฟลเดอร์ของเรา
                    for change in changes:
                        file_info = change.get('file')
                        if not file_info:
                            continue

                        if (file_info.get('mimeType') in ['image/jpeg', 'image/png', 'image/jpg'] and
                            folder_id in file_info.get('parents', []) and
                            not file_info.get('trashed', False)):

                            file_id = file_info['id']
                            if file_id not in processed_ids:
                                new_photos.append({
                                    'id': file_id,
                                    'name': file_info['name']
                                })

                    # อัพเดท token
                    if 'newStartPageToken' in response:
                        new_page_token = response['newStartPageToken']
                        break

                    new_page_token = response.get('nextPageToken')
                    if not new_page_token:
                        break

                except HttpError as e:
                    if e.resp.status == 400:
                        # Token หมดอายุ → reinitialize
                        logger.warning("Page token หมดอายุ, reinitialize...")
                        response = drive_service.changes().getStartPageToken().execute()
                        new_page_token = response.get('startPageToken')
                        break
                    raise

            # บันทึก token ใหม่
            db_conn.execute(
                'UPDATE events SET drive_page_token = ? WHERE id = ?',
                (new_page_token, event_id)
            )
            db_conn.commit()

        total_new_photos = len(new_photos)

        if total_new_photos == 0:
            logger.info("ไม่พบภาพใหม่")
            db_conn.execute(
                "UPDATE events SET indexing_status = ? WHERE id = ?",
                ('Completed', event_id)
            )
            db_conn.commit()
            task.complete()
            return

        logger.info(f"พบ {total_new_photos} ภาพใหม่")

        # ดึงข้อมูลปัจจุบัน
        current_data = db_conn.execute(
            'SELECT indexed_photos, total_faces FROM events WHERE id = ?',
            (event_id,)
        ).fetchone()

        indexed_photos = current_data['indexed_photos'] or 0
        total_faces = current_data['total_faces'] or 0

        # ประมวลผลภาพใหม่
        new_indexed = 0
        new_faces = 0

        for i, photo in enumerate(new_photos):
            photo_id = photo['id']
            photo_name = photo['name']

            task.update_progress(i, total_new_photos, photo_name, faces_found=total_faces + new_faces)

            try:
                faces_found = index_single_photo(
                    drive_service,
                    db_conn,
                    event_id,
                    photo_id,
                    photo_name,
                    config
                )

                new_faces += faces_found
                new_indexed += 1

                # บันทึก checkpoint
                face_database.save_checkpoint(db_conn, event_id, photo_id, photo_name, faces_found)

                # อัพเดท progress
                db_conn.execute(
                    "UPDATE events SET indexed_photos = ?, total_faces = ? WHERE id = ?",
                    (indexed_photos + new_indexed, total_faces + new_faces, event_id)
                )
                db_conn.commit()

            except Exception as e:
                logger.error(f"Error ในการประมวลผล {photo_name}: {e}")

        # อัพเดทสถานะสุดท้าย
        db_conn.execute(
            "UPDATE events SET indexing_status = ?, indexed_photos = ?, total_faces = ? WHERE id = ?",
            ('Completed', indexed_photos + new_indexed, total_faces + new_faces, event_id)
        )
        db_conn.commit()

        # ลบ checkpoints
        face_database.clear_checkpoints(db_conn, event_id)

        task.complete()
        logger.info(f"Incremental Indexing เสร็จสิ้น: ภาพใหม่ {new_indexed}, ใบหน้าใหม่ {new_faces}")

    except HttpError as e:
        error_msg = f"Google Drive API error: {e}"
        logger.error(error_msg)
        task.fail(error_msg)
        db_conn.execute("UPDATE events SET indexing_status = ? WHERE id = ?", ('Failed', event_id))
        db_conn.commit()

    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        logger.error(error_msg, exc_info=True)
        task.fail(error_msg)
        db_conn.execute("UPDATE events SET indexing_status = ? WHERE id = ?", ('Failed', event_id))
        db_conn.commit()


# Export public API
__all__ = [
    'run_full_indexing',
    'run_incremental_indexing',
    'index_single_photo',
    'download_image_from_drive',
    'ensure_drive_token_column',
    'IndexingError',
]
