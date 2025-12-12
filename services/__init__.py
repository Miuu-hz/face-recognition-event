"""
Services Package สำหรับ Face Recognition Event System

โมดูลหลัก:
- face_encoder: การตรวจจับและสร้าง face encodings
- face_matcher: การค้นหาและจับคู่ใบหน้า
- face_database: การจัดการฐานข้อมูล face encodings
- indexing_service: การ index ภาพจาก Google Drive
- search_service: การค้นหาใบหน้าจาก selfies

การใช้งาน:
    from services import face_encoder, face_matcher, face_database
    from services import indexing_service, search_service

    # Encode face
    faces = face_encoder.extract_face_encodings('photo.jpg')

    # Search matches
    result = face_matcher.find_matches(db, event_id, encoding)

    # Run indexing
    indexing_service.run_full_indexing(task, event_id, folder_id, creds, db, config)

    # Search by selfies
    result = search_service.search_faces_by_selfies(db, event_id, files, tolerance, config)
"""

from .face_encoder import (
    extract_face_encodings,
    create_average_encoding,
    batch_extract_encodings,
    get_face_count,
    FaceEncoderConfig,
    ImageProcessingError,
    config as encoder_config
)

from .face_matcher import (
    find_matches,
    find_matches_cosine,
    batch_find_matches,
    load_encodings_from_db,
    FaceCache,
    FaceMatcherError,
    cache as matcher_cache
)

from .face_database import (
    save_face_to_db,
    save_faces_batch,
    get_faces_by_event,
    get_indexed_photo_ids,
    delete_faces_by_event,
    get_face_count_by_event,
    ensure_checkpoint_table,
    get_checkpoints,
    save_checkpoint,
    clear_checkpoints,
    count_checkpoints,
    get_checkpoint_photo_ids,
    FaceDatabaseError,
)

from .indexing_service import (
    run_full_indexing,
    run_incremental_indexing,
    index_single_photo,
    download_image_from_drive,
    ensure_drive_token_column,
    IndexingError,
)

from .search_service import (
    search_faces_by_selfies,
    process_uploaded_images,
    validate_uploaded_files,
    format_search_results,
    get_top_matches,
    cleanup_temp_files,
    SearchError,
)

__version__ = '2.0.0'

__all__ = [
    # Face Encoder
    'extract_face_encodings',
    'create_average_encoding',
    'batch_extract_encodings',
    'get_face_count',
    'FaceEncoderConfig',
    'ImageProcessingError',
    'encoder_config',

    # Face Matcher
    'find_matches',
    'find_matches_cosine',
    'batch_find_matches',
    'load_encodings_from_db',
    'FaceCache',
    'FaceMatcherError',
    'matcher_cache',

    # Face Database
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

    # Indexing Service
    'run_full_indexing',
    'run_incremental_indexing',
    'index_single_photo',
    'download_image_from_drive',
    'ensure_drive_token_column',
    'IndexingError',

    # Search Service
    'search_faces_by_selfies',
    'process_uploaded_images',
    'validate_uploaded_files',
    'format_search_results',
    'get_top_matches',
    'cleanup_temp_files',
    'SearchError',
]
