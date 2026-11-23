"""JARVIS Biometric Enrollment Utility.

Run this script directly to capture your face using the webcam.
The captured image will be saved as `authorized_user.jpg` in the project root,
allowing the face_monitor daemon to verify your identity.
"""

import os
import sys

import cv2


def enroll_face():
    print("=========================================")
    print(" JARVIS Biometric Enrollment")
    print("=========================================")
    print("Initializing webcam...")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] Could not open webcam.")
        sys.exit(1)

    print("\nInstructions:")
    print("1. Look directly at the camera.")
    print("2. Ensure you are in a well-lit environment.")
    print("3. Press 'SPACE' to capture your face.")
    print("4. Press 'ESC' or 'q' to cancel.")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[ERROR] Failed to grab frame.")
            break

        # Draw a guide rectangle
        h, w = frame.shape[:2]
        cv2.rectangle(frame, (w // 4, h // 4), (w * 3 // 4, h * 3 // 4), (0, 255, 0), 2)
        cv2.putText(
            frame,
            "Position face inside box",
            (w // 4, h // 4 - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2,
        )

        cv2.imshow("JARVIS Enrollment", frame)

        key = cv2.waitKey(1)
        if key % 256 == 27 or key % 256 == ord("q"):
            # ESC pressed
            print("\nEnrollment cancelled.")
            break
        elif key % 256 == 32:
            # SPACE pressed
            root_dir = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            img_path = os.path.join(root_dir, "authorized_user.jpg")

            # Save the clean frame (without the green box)
            ret_clean, clean_frame = cap.read()
            if ret_clean:
                cv2.imwrite(img_path, clean_frame)
                print(f"\n[SUCCESS] Face enrolled! Saved to {img_path}")
                print("JARVIS will now recognize you.")
            else:
                print("\n[ERROR] Failed to capture clean frame.")
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    enroll_face()
