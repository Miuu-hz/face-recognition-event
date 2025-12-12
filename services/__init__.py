"""
Services Package สำหรับ Face Recognition Event System

โมดูลหลัก:
- face_encoder: การตรวจจับและสร้าง face encodings
- face_matcher: การค้นหาและจับคู่ใบหน้า

การใช้งาน:
    from services import face_encoder, face_matcher

    # Encode face
    faces = face_encoder.extract_face_encodings('photo.jpg')

    # Search matches
    result = face_matcher.find_matches(db, event_id, encoding)
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

__version__ = '1.0.0'

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
]
