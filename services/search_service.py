"""
โมดูลสำหรับ Face Search Service
จัดการการค้นหาใบหน้าจากภาพ selfie ที่ผู้ใช้อัพโหลด

ฟีเจอร์หลัก:
- ประมวลผลภาพ selfie หลายภาพ
- สร้าง average encoding เพื่อ accuracy ที่ดีขึ้น
- ค้นหาภาพที่ตรงกันจาก database
- จัดเรียงผลลัพธ์ตาม confidence
"""

import os
import logging
import tempfile
from . import face_encoder, face_matcher

logger = logging.getLogger('face_recognition_app')


class SearchError(Exception):
    """Exception สำหรับ error ในการค้นหา"""
    pass


def process_uploaded_images(uploaded_files, config):
    """ประมวลผลภาพ selfie ที่ผู้ใช้อัพโหลด

    Args:
        uploaded_files (list): รายการ FileStorage objects
        config (dict): configuration {'model': str, 'num_jitters': int}

    Returns:
        dict: {
            'encodings': list of numpy arrays,
            'temp_files': list of paths (ต้องลบภายหลัง),
            'face_count': int
        }

    Raises:
        SearchError: ถ้าไม่พบใบหน้าหรือเกิด error
    """
    uploaded_encodings = []
    temp_files = []

    try:
        for file in uploaded_files:
            if file and file.filename != '':
                # บันทึกลง temp file
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
                file.save(temp_file.name)
                temp_files.append(temp_file.name)

                logger.debug(f"ประมวลผล selfie: {file.filename}")

                # Extract face encodings
                try:
                    faces = face_encoder.extract_face_encodings(
                        temp_file.name,
                        model=config.get('model', 'hog'),
                        num_jitters=config.get('num_jitters', 1)
                    )

                    if faces:
                        # ใช้ใบหน้าแรกที่พบ
                        uploaded_encodings.append(faces[0]['encoding'])
                        logger.debug(f"พบใบหน้าใน {file.filename}")
                    else:
                        logger.warning(f"ไม่พบใบหน้าใน {file.filename}")

                except face_encoder.ImageProcessingError as e:
                    logger.warning(f"ข้าม {file.filename}: {e}")

        if not uploaded_encodings:
            raise SearchError("ไม่พบใบหน้าในภาพที่อัพโหลด กรุณาลองใหม่ด้วยภาพที่ชัดเจน")

        return {
            'encodings': uploaded_encodings,
            'temp_files': temp_files,
            'face_count': len(uploaded_encodings)
        }

    except SearchError:
        # ลบ temp files ก่อน raise
        cleanup_temp_files(temp_files)
        raise

    except Exception as e:
        cleanup_temp_files(temp_files)
        error_msg = f"ไม่สามารถประมวลผลภาพ: {e}"
        logger.error(error_msg)
        raise SearchError(error_msg)


def cleanup_temp_files(temp_files):
    """ลบ temporary files

    Args:
        temp_files (list): รายการ paths ของ temp files
    """
    for temp_file in temp_files:
        try:
            if os.path.exists(temp_file):
                os.remove(temp_file)
                logger.debug(f"ลบ temp file: {temp_file}")
        except Exception as e:
            logger.warning(f"ไม่สามารถลบ temp file {temp_file}: {e}")


def search_faces_by_selfies(db_conn, event_id, uploaded_files, tolerance, config):
    """ค้นหาภาพที่ตรงกับ selfies ที่อัพโหลด

    Workflow:
    1. ประมวลผล selfies → ได้ encodings
    2. สร้าง average encoding (ถ้ามีหลายภาพ)
    3. ค้นหาจาก database
    4. จัดเรียงผลลัพธ์

    Args:
        db_conn: database connection
        event_id (str): ID ของ event
        uploaded_files (list): รายการ FileStorage objects
        tolerance (float): threshold สำหรับการจับคู่
        config (dict): configuration

    Returns:
        dict: {
            'matches': [{'photo_id': str, 'photo_name': str, 'distance': float, 'url': str}, ...],
            'faces_checked': int,
            'selfies_processed': int,
            'total_matches': int
        }

    Raises:
        SearchError: ถ้าเกิด error ในการค้นหา
    """
    temp_files = []

    try:
        # 1. ประมวลผล selfies
        logger.info(f"เริ่มค้นหาสำหรับ event {event_id} ด้วย {len(uploaded_files)} selfies")

        processed = process_uploaded_images(uploaded_files, config)
        uploaded_encodings = processed['encodings']
        temp_files = processed['temp_files']
        selfies_count = processed['face_count']

        logger.info(f"ประมวลผล selfies สำเร็จ: พบ {selfies_count} ใบหน้า")

        # 2. สร้าง average encoding
        if len(uploaded_encodings) > 1:
            search_encoding = face_encoder.create_average_encoding(uploaded_encodings)
            logger.info(f"สร้าง average encoding จาก {len(uploaded_encodings)} ภาพ")
        else:
            search_encoding = uploaded_encodings[0]
            logger.info("ใช้ encoding จากภาพเดียว")

        # 3. ค้นหาจาก database
        logger.info(f"เริ่มค้นหาใน database (tolerance={tolerance})...")

        search_result = face_matcher.find_matches(
            db_conn,
            event_id,
            search_encoding,
            tolerance=tolerance,
            use_cache=True
        )

        matches = search_result['matches']
        faces_checked = search_result['faces_checked']

        logger.info(f"ค้นหาเสร็จสิ้น: ตรวจสอบ {faces_checked} ใบหน้า, พบ {len(matches)} ภาพ")

        # 4. เพิ่ม Google Drive URLs
        for match in matches:
            match['url'] = f"https://drive.google.com/file/d/{match['photo_id']}/view"

        # จัดเรียงตาม distance (ต่ำสุดก่อน = คล้ายที่สุด)
        matches.sort(key=lambda x: x['distance'])

        return {
            'matches': matches,
            'faces_checked': faces_checked,
            'selfies_processed': selfies_count,
            'total_matches': len(matches),
            'tolerance_used': tolerance,
            'used_cache': search_result.get('used_cache', False)
        }

    except SearchError:
        raise

    except face_matcher.FaceMatcherError as e:
        error_msg = f"ไม่สามารถค้นหา faces: {e}"
        logger.error(error_msg)
        raise SearchError(error_msg)

    except Exception as e:
        error_msg = f"Unexpected error ในการค้นหา: {e}"
        logger.error(error_msg, exc_info=True)
        raise SearchError(error_msg)

    finally:
        # ลบ temp files
        cleanup_temp_files(temp_files)


def get_top_matches(matches, limit=10):
    """ดึง top N matches

    Args:
        matches (list): รายการ matches ทั้งหมด
        limit (int): จำนวนสูงสุดที่ต้องการ

    Returns:
        list: top N matches
    """
    # เรียงตาม distance (ต่ำสุด = ดีที่สุด)
    sorted_matches = sorted(matches, key=lambda x: x.get('distance', 1.0))
    return sorted_matches[:limit]


def format_search_results(search_result, limit=None):
    """จัดรูปแบบผลลัพธ์สำหรับ API response

    Args:
        search_result (dict): ผลลัพธ์จาก search_faces_by_selfies()
        limit (int, optional): จำกัดจำนวนผลลัพธ์

    Returns:
        dict: formatted results
    """
    matches = search_result['matches']

    if limit:
        matches = get_top_matches(matches, limit)

    return {
        'success': True,
        'matches': [
            {
                'photo_id': m['photo_id'],
                'photo_name': m['photo_name'],
                'url': m['url'],
                'confidence': round((1 - m['distance']) * 100, 2),  # แปลงเป็น %
                'distance': round(m['distance'], 3)
            }
            for m in matches
        ],
        'stats': {
            'total_matches': search_result['total_matches'],
            'faces_checked': search_result['faces_checked'],
            'selfies_processed': search_result['selfies_processed'],
            'tolerance': search_result.get('tolerance_used', 0.5),
            'used_cache': search_result.get('used_cache', False)
        }
    }


def validate_uploaded_files(uploaded_files, max_files=3, max_size_mb=10):
    """ตรวจสอบไฟล์ที่อัพโหลด

    Args:
        uploaded_files (list): รายการ FileStorage objects
        max_files (int): จำนวนไฟล์สูงสุด
        max_size_mb (int): ขนาดไฟล์สูงสุด (MB)

    Raises:
        SearchError: ถ้าไฟล์ไม่ผ่านการตรวจสอบ
    """
    if not uploaded_files:
        raise SearchError("ไม่มีไฟล์ที่อัพโหลด")

    if len(uploaded_files) > max_files:
        raise SearchError(f"อัพโหลดได้สูงสุด {max_files} ไฟล์")

    allowed_extensions = {'jpg', 'jpeg', 'png', 'gif'}
    max_size_bytes = max_size_mb * 1024 * 1024

    for file in uploaded_files:
        if not file or file.filename == '':
            continue

        # ตรวจสอบ extension
        filename = file.filename.lower()
        if not any(filename.endswith(f'.{ext}') for ext in allowed_extensions):
            raise SearchError(f"ประเภทไฟล์ไม่รองรับ: {file.filename}. อนุญาตเฉพาะ: {', '.join(allowed_extensions)}")

        # ตรวจสอบขนาด
        file.seek(0, 2)  # Seek to end
        size = file.tell()
        file.seek(0)  # Reset

        if size > max_size_bytes:
            raise SearchError(f"ไฟล์ {file.filename} ใหญ่เกิน {max_size_mb}MB")

    logger.debug(f"Validation passed: {len(uploaded_files)} files")


# Export public API
__all__ = [
    'search_faces_by_selfies',
    'process_uploaded_images',
    'validate_uploaded_files',
    'format_search_results',
    'get_top_matches',
    'cleanup_temp_files',
    'SearchError',
]
