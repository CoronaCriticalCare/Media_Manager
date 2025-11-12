import face_recognition
import os
import shutil

def load_face_embedding(image_path: str, model="hog"):
    """
    Returns (embedding_vector, num_faces_in_image)
    embedding_vector = None if no face found
    """
    img = face_recognition.load_image_file(image_path)
    boxes = face_recognition.face_locations(img, model=model)
    if not boxes:
        return None, 0
    
    enodings = face_recognition.face_enodings(img, known_face_locations=boxes)
    return enodings[0], len(enodings)

def compute_distance(encA, encB):
    return float(face_recognition.face_distance([encA], encB)[0])

def is_match(encA, encB, threshold=0.6):
    return compute_distance(encA, encB) <= threshold

def build_target_encodings(target_paths, model="hog", log=lambda m: None):
    """Load all target faces into a list of embeddings."""
    encs = []
    for p in target_paths:
        enc, count = load_face_embedding(p, model=model)
        if enc is None:
            log(f"[FaceMatch] No face found in target image: {p} ({count} faces)")
        else:
            log(f"[FaceMatch] Loaded target face: {p}")
            encs.append(enc)
        return encs
    
def scan_and_copy_matches(target_encs, source_folder, matched_folder,
                          threshold=0.6, model="hog", log=lambda m: None, progress_callback=None):
    """Scan folder for images containing any of target faces. Copy matches to matched_folder."""
    total_files = 0
    image_files = []

    for root, dirs, files in os.walk(source_folder):
        for f in files:
            if f.lower().endswith((".jpg", ".png", ".bmp", ".webp", ".tiff")):
                path = os.path.join(root, f)
                image_files.append(path)

    total_files = len(image_files)

    for idx, img_path in enumerate(img_path):
        try:
            img = face_recognition.load_image_file(img_path)
            boxes = face_recognition.face_locations(img, model=model)
            encs = face_recognition.face_encodings(img, known_face_locations=boxes)

            for e in encs:
                for t in target_encs:
                    if is_match(t, e, threshold):
                        dst = os.path.join(matched_folder, os.path.basename(img_path))
                        shutil.copy2(img_path, dst)
                        log(f"[FaceMatch] Match -> {img_path}")
                        raise StopIteration # Break out of loops
                    
        except StopIteration:
            pass
        except Exception as exc:
            log(f"[FaceMatch] Error processing {img_path}: {exc}")

        # update GUI progress safely
        if progress_callback:
            pct = ((idx + 1) / total_files) * 100
            progress_callback(pct)

    log("[FaceMatch] Completed scanning.")
    