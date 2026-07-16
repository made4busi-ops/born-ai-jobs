#!/usr/bin/env python3
"""
Guard 1: Face Match
Checks whether a generated hero-scene video actually still shows the
same person as the reference photo. First checkpoint -- catches
identity drift before a scene ships to a customer.

Threshold: face_recognition distance <= 0.6 (their recommended cutoff
for "same person" -- lower distance = more similar).
"""
import face_recognition

GUARD_NAME = "face_match"
THRESHOLD = 0.6


def check(reference_photo_path: str, generated_frame_path: str) -> dict:
    try:
        ref_image = face_recognition.load_image_file(reference_photo_path)
        ref_encodings = face_recognition.face_encodings(ref_image)
        if not ref_encodings:
            return {"guard": GUARD_NAME, "passed": False, "score": None,
                    "reason": "No face detected in reference photo"}

        gen_image = face_recognition.load_image_file(generated_frame_path)
        gen_encodings = face_recognition.face_encodings(gen_image)
        if not gen_encodings:
            return {"guard": GUARD_NAME, "passed": False, "score": None,
                    "reason": "No face detected in generated frame"}

        distance = face_recognition.face_distance([ref_encodings[0]], gen_encodings[0])[0]
        passed = bool(distance <= THRESHOLD)

        return {"guard": GUARD_NAME, "passed": passed, "score": round(float(distance), 4),
                "reason": "OK" if passed else f"Face distance {distance:.4f} exceeds threshold {THRESHOLD}"}
    except Exception as e:
        return {"guard": GUARD_NAME, "passed": False, "score": None, "reason": f"Guard error: {e}"}
