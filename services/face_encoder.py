"""
โมดูลสำหรับ Face Encoding
จัดการการตรวจจับใบหน้าและสร้าง 128-dimensional face embeddings

ฟีเจอร์หลัก:
- ตรวจจับใบหน้าใน image โดยใช้ dlib (HOG/CNN model)
- สร้าง 128-dimensional face encodings
- สร้าง average encoding จากหลายภาพ
- รองรับทั้ง CPU และ GPU
"""

import os
import logging
import numpy as np
import face_recognition

logger = logging.getLogger('face_recognition_app')


class ImageProcessingError(Exception):
    """Exception สำหรับ error ในการประมวลผลภาพ"""
    pass


def detect_gpu():
    """ตรวจสอบว่ามี GPU สำหรับ face recognition หรือไม่

    Returns:
        bool: True ถ้ามี GPU, False ถ้าใช้ CPU
    """
    # Method 1: ตรวจสอบว่า dlib มี CUDA support หรือไม่
    try:
        import dlib
        if hasattr(dlib, 'DLIB_USE_CUDA') and dlib.DLIB_USE_CUDA:
            return True
    except:
        pass

    # Method 2: ตรวจสอบ nvidia-smi
    try:
        import subprocess
        result = subprocess.run(
            ['nvidia-smi'],
            capture_output=True,
            text=True,
            timeout=2
        )
        return result.returncode == 0
    except:
        pass

    return False


# ตรวจสอบ GPU และเลือก model อัตโนมัติ
HAS_GPU = detect_gpu()
DEFAULT_MODEL = 'cnn' if HAS_GPU else 'hog'


class FaceEncoderConfig:
    """การตั้งค่าสำหรับ Face Encoder"""

    def __init__(self):
        self.model = os.getenv('FACE_MODEL', DEFAULT_MODEL)
        self.tolerance = float(os.getenv('FACE_TOLERANCE', '0.5'))
        self.num_jitters = int(os.getenv('NUM_JITTERS', '1'))
        self.batch_size = int(os.getenv('BATCH_SIZE', '20'))
        self.has_gpu = HAS_GPU

    def to_dict(self):
        """แปลง config เป็น dictionary"""
        return {
            'model': self.model,
            'tolerance': self.tolerance,
            'num_jitters': self.num_jitters,
            'batch_size': self.batch_size,
            'has_gpu': self.has_gpu
        }

    def print_config(self):
        """แสดงการตั้งค่าปัจจุบัน"""
        print("\n" + "="*50)
        print("Face Encoder Configuration:")
        print("="*50)
        print(f"Device:       {'GPU (CUDA)' if self.has_gpu else 'CPU'}")
        print(f"Model:        {self.model.upper()} ({'CNN - High Accuracy' if self.model == 'cnn' else 'HOG - Fast'})")
        print(f"Tolerance:    {self.tolerance} (ยิ่งต่ำ = ยิ่งเข้มงวด)")
        print(f"Batch Size:   {self.batch_size} ภาพ")
        print(f"Num Jitters:  {self.num_jitters}")
        print("="*50 + "\n")


# สร้าง global config instance
config = FaceEncoderConfig()


def extract_face_encodings(image_path, model=None, num_jitters=None):
    """ดึง face encodings จากภาพ

    Args:
        image_path (str): path ไปยังไฟล์ภาพ
        model (str, optional): 'hog' หรือ 'cnn'. ถ้าไม่ระบุจะใช้จาก config
        num_jitters (int, optional): จำนวนครั้งที่ resample. ถ้าไม่ระบุจะใช้จาก config

    Returns:
        list: รายการ dict ที่มี 'encoding' และ 'location' ของแต่ละใบหน้า

    Raises:
        ImageProcessingError: ถ้าไม่สามารถประมวลผลภาพได้

    ตัวอย่าง:
        >>> faces = extract_face_encodings('photo.jpg')
        >>> print(f"พบ {len(faces)} ใบหน้า")
        >>> for face in faces:
        ...     print(f"Location: {face['location']}")
        ...     print(f"Encoding shape: {face['encoding'].shape}")
    """
    if model is None:
        model = config.model
    if num_jitters is None:
        num_jitters = config.num_jitters

    try:
        # โหลดภาพ
        image = face_recognition.load_image_file(image_path)

        # หาตำแหน่งใบหน้า
        face_locations = face_recognition.face_locations(image, model=model)

        # สร้าง encodings
        face_encodings = face_recognition.face_encodings(
            image,
            face_locations,
            num_jitters=num_jitters
        )

        # จัดรูปแบบผลลัพธ์
        results = []
        for location, encoding in zip(face_locations, face_encodings):
            results.append({
                'encoding': encoding,
                'location': {
                    'top': location[0],
                    'right': location[1],
                    'bottom': location[2],
                    'left': location[3]
                }
            })

        logger.debug(f"พบ {len(results)} ใบหน้าใน {image_path}")
        return results

    except Exception as e:
        error_msg = f"ไม่สามารถประมวลผล {image_path}: {e}"
        logger.error(error_msg)
        raise ImageProcessingError(error_msg)


def create_average_encoding(encodings):
    """สร้าง average encoding จากหลาย face encodings

    เหมาะสำหรับกรณีที่มีหลายภาพของคนเดียวกัน เช่น:
    - ผู้ใช้อัพโหลด 3 ภาพ selfie → สร้าง average เพื่อ accuracy ที่ดีขึ้น
    - มีหลายมุมของใบหน้าเดียวกัน → average จะ robust กับมุมต่างๆ

    Args:
        encodings (list): รายการของ numpy arrays (face encodings)

    Returns:
        numpy.ndarray: average encoding หรือ None ถ้า input ว่าง

    ตัวอย่าง:
        >>> selfie1 = extract_face_encodings('selfie1.jpg')[0]['encoding']
        >>> selfie2 = extract_face_encodings('selfie2.jpg')[0]['encoding']
        >>> selfie3 = extract_face_encodings('selfie3.jpg')[0]['encoding']
        >>> avg_encoding = create_average_encoding([selfie1, selfie2, selfie3])
        >>> print(f"Average encoding shape: {avg_encoding.shape}")
    """
    if len(encodings) == 0:
        logger.warning("ไม่มี encodings ให้ทำ average")
        return None
    elif len(encodings) == 1:
        logger.debug("มี encoding เดียว ไม่ต้องทำ average")
        return encodings[0]
    else:
        logger.debug(f"สร้าง average encoding จาก {len(encodings)} ภาพ")
        return np.mean(encodings, axis=0)


def batch_extract_encodings(image_paths, model=None, num_jitters=None):
    """ดึง encodings จากหลายภาพพร้อมกัน (batch processing)

    Args:
        image_paths (list): รายการ paths ของภาพ
        model (str, optional): model ที่ใช้
        num_jitters (int, optional): จำนวน jitters

    Returns:
        dict: {image_path: [list of face data], ...}

    ตัวอย่าง:
        >>> paths = ['photo1.jpg', 'photo2.jpg', 'photo3.jpg']
        >>> results = batch_extract_encodings(paths)
        >>> for path, faces in results.items():
        ...     print(f"{path}: พบ {len(faces)} ใบหน้า")
    """
    results = {}
    total = len(image_paths)

    logger.info(f"เริ่ม batch processing {total} ภาพ...")

    for i, image_path in enumerate(image_paths):
        try:
            faces = extract_face_encodings(image_path, model, num_jitters)
            results[image_path] = faces

            if (i + 1) % 10 == 0:
                logger.info(f"ประมวลผลแล้ว {i + 1}/{total} ภาพ")

        except ImageProcessingError as e:
            logger.warning(f"ข้าม {image_path}: {e}")
            results[image_path] = []

    logger.info(f"Batch processing เสร็จสิ้น: {total} ภาพ")
    return results


def get_face_count(image_path, model=None):
    """นับจำนวนใบหน้าในภาพอย่างรวดเร็ว (ไม่สร้าง encoding)

    Args:
        image_path (str): path ของภาพ
        model (str, optional): model ที่ใช้

    Returns:
        int: จำนวนใบหน้าที่พบ

    ตัวอย่าง:
        >>> count = get_face_count('group_photo.jpg')
        >>> print(f"พบ {count} ใบหน้า")
    """
    if model is None:
        model = config.model

    try:
        image = face_recognition.load_image_file(image_path)
        face_locations = face_recognition.face_locations(image, model=model)
        return len(face_locations)
    except Exception as e:
        logger.error(f"ไม่สามารถนับใบหน้าใน {image_path}: {e}")
        return 0


# Export public API
__all__ = [
    'extract_face_encodings',
    'create_average_encoding',
    'batch_extract_encodings',
    'get_face_count',
    'FaceEncoderConfig',
    'ImageProcessingError',
    'config'
]
