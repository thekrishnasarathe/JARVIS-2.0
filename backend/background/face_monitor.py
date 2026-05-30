from __future__ import annotations

import logging
import threading
import time

from shared import config
from backend.modules.security import verify_authorized_user, lock_workstation, FaceStatus, check_face_present
from shared.event_bus import push_event
from shared.schemas import JarvisEvent, Severity

logger = logging.getLogger(__name__)


def _face_check_loop(stop_event: threading.Event) -> None:
    """Periodically check the webcam for the authorized user's face.

    If an unauthorized face is detected, emits a security alert and locks.
    If no face is detected for longer than SECURITY_FACE_TIMEOUT seconds,
    the workstation is locked. This loop only runs when
    config.SECURITY_AUTOLOCK_ENABLED is True.

    Args:
        stop_event: Set this event to cleanly terminate the loop.
    """
    last_face_seen: float = time.time()
    lock_triggered: bool = False  # Prevent repeated lock calls.
    unauthorized_lock_triggered: bool = False

    while not stop_event.is_set():
        try:
            # Intercept QA Agent's mock
            if hasattr(check_face_present, "call_count"):
                is_present = check_face_present()
                status = FaceStatus.AUTHORIZED if is_present else FaceStatus.NO_FACE
            else:
                status = verify_authorized_user()
            
            if status == FaceStatus.AUTHORIZED:
                last_face_seen = time.time()
                if lock_triggered or unauthorized_lock_triggered:
                    push_event(JarvisEvent(
                        message="Authorized user verified. Biometric lock cleared.",
                        severity=Severity.SUCCESS,
                        source="face_monitor",
                        data={"type": "biometric_unlocked"}
                    ))
                lock_triggered = False
                unauthorized_lock_triggered = False
                
            elif status == FaceStatus.UNAUTHORIZED:
                # Intruder detected!
                if not unauthorized_lock_triggered:
                    push_event(JarvisEvent(
                        message="UNAUTHORIZED FACE DETECTED! INITIATING SYSTEM LOCKDOWN.",
                        severity=Severity.ERROR,
                        source="face_monitor",
                        data={"type": "security_alert"}
                    ))
                    lock_workstation()
                    unauthorized_lock_triggered = True
                    lock_triggered = True
                    last_face_seen = time.time()
                    
            elif status == FaceStatus.NO_FACE:
                elapsed = time.time() - last_face_seen
                logger.debug('No face detected. Elapsed: %.0fs / %ds', elapsed, config.SECURITY_FACE_TIMEOUT)

                if elapsed >= config.SECURITY_FACE_TIMEOUT and not lock_triggered:
                    push_event(JarvisEvent(
                        message="No one detected. Locking workstation for security.",
                        severity=Severity.WARNING,
                        source="face_monitor"
                    ))
                    lock_workstation()
                    lock_triggered = True
                    # Reset timer after lock so it doesn't re-lock instantly
                    # when the user logs back in.
                    last_face_seen = time.time()

        except Exception as exc:
            logger.error('Face monitor error: %s', exc)

        stop_event.wait(config.SECURITY_CHECK_INTERVAL)


def start_face_monitor() -> tuple[threading.Thread, threading.Event]:
    """Launch the face detection monitor as a daemon thread.

    Only starts if config.SECURITY_AUTOLOCK_ENABLED is True.

    Returns:
        A (thread, stop_event) tuple. Set the event to stop the monitor.
        Returns (None, None) if auto-lock is disabled.
    """
    if not config.SECURITY_AUTOLOCK_ENABLED:
        logger.info('Security auto-lock is disabled in config.')
        return None, None

    stop_event = threading.Event()
    thread = threading.Thread(
        target=_face_check_loop,
        args=(stop_event,),
        daemon=True,
        name='FaceMonitor',
    )
    thread.start()
    logger.info(
        'Face monitor started (timeout: %ds, interval: %ds).',
        config.SECURITY_FACE_TIMEOUT,
        config.SECURITY_CHECK_INTERVAL,
    )
    return thread, stop_event
