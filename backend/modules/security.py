"""Webcam face detection utilities for security / workstation lock."""

from __future__ import annotations

import logging
import os
from enum import Enum

logger = logging.getLogger(__name__)


class FaceStatus(Enum):
    NO_FACE = 0
    AUTHORIZED = 1
    UNAUTHORIZED = 2


# Lazy-load the cascade classifier to avoid import-time failures
# when opencv-python is not installed.
_face_cascade = None
_authorized_encoding = None
_face_recognition_available = False
_face_recognition_initialized = False


def _get_face_cascade():
    """Lazy-initialize the Haar cascade face classifier."""
    global _face_cascade
    if _face_cascade is not None:
        return _face_cascade

    try:
        import cv2

        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        _face_cascade = cv2.CascadeClassifier(cascade_path)
        if _face_cascade.empty():
            logger.error("Haar cascade file failed to load from: %s", cascade_path)
            _face_cascade = None
        return _face_cascade
    except Exception as exc:
        logger.error("OpenCV initialization error: %s", exc)
        return None


def _init_face_recognition():
    """Attempt to load face_recognition and encode authorized_user.jpg."""
    global _authorized_encoding, _face_recognition_available, _face_recognition_initialized
    if _face_recognition_initialized:
        return

    _face_recognition_initialized = True
    try:
        import face_recognition

        # Look for authorized_user.jpg in the project root
        root_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        img_path = os.path.join(root_dir, "authorized_user.jpg")

        if os.path.exists(img_path):
            image = face_recognition.load_image_file(img_path)
            encodings = face_recognition.face_encodings(image)
            if encodings:
                _authorized_encoding = encodings[0]
                _face_recognition_available = True
                logger.info(
                    "Successfully loaded authorized_user.jpg for biometric lock."
                )
            else:
                logger.warning("No face found in authorized_user.jpg")
        else:
            logger.warning(
                "authorized_user.jpg not found. Falling back to any-face detection."
            )
    except ImportError:
        logger.warning(
            "face_recognition library not installed. Falling back to basic OpenCV detection."
        )
    except Exception as exc:
        logger.error("Error initializing face_recognition: %s", exc)


def verify_authorized_user() -> FaceStatus:
    """Capture a single webcam frame and verify against authorized user.

    Returns:
        FaceStatus.AUTHORIZED if the authorized user is detected.
        FaceStatus.UNAUTHORIZED if a face is detected but is not authorized.
        FaceStatus.NO_FACE if no human face is detected.
    """
    _init_face_recognition()

    try:
        import cv2

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            logger.warning("Webcam could not be opened.")
            return FaceStatus.NO_FACE

        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            logger.warning("Failed to capture frame from webcam.")
            return FaceStatus.NO_FACE

        if _face_recognition_available and _authorized_encoding is not None:
            import face_recognition

            # Convert the image from BGR color (which OpenCV uses) to RGB color (which face_recognition uses)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Find all the faces and face encodings in the current frame
            face_locations = face_recognition.face_locations(rgb_frame)
            if not face_locations:
                return FaceStatus.NO_FACE

            face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

            for face_encoding in face_encodings:
                matches = face_recognition.compare_faces(
                    [_authorized_encoding], face_encoding, tolerance=0.6
                )
                if matches[0]:
                    return FaceStatus.AUTHORIZED

            # A face was found, but it didn't match the authorized encoding
            return FaceStatus.UNAUTHORIZED

        else:
            # Fallback to Haar Cascades (Basic any-face detection)
            cascade = _get_face_cascade()
            if cascade is None:
                return FaceStatus.NO_FACE

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, scaleFactor=1.3, minNeighbors=5)

            if len(faces) > 0:
                # If we don't have biometrics enabled, any face is considered "authorized"
                return FaceStatus.AUTHORIZED
            else:
                return FaceStatus.NO_FACE

    except Exception as exc:
        logger.error("Face verification error: %s", exc)
        return FaceStatus.NO_FACE


# Keep backward compatibility for QA tests that might still use this hook
def check_face_present() -> bool:
    """Legacy wrapper for QA tests."""
    return verify_authorized_user() == FaceStatus.AUTHORIZED


def lock_workstation() -> None:
    """Lock the Windows workstation.

    Calls the Win32 API via rundll32. This is a no-op on non-Windows
    platforms (logged as a warning).
    """
    if os.name == "nt":
        logger.info("Locking workstation — security event triggered.")
        os.system("rundll32.exe user32.dll,LockWorkStation")
    else:
        logger.warning("Workstation lock is only supported on Windows.")
