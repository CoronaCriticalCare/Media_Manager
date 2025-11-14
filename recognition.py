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
    
    encodings = face_recognition.face_encodings(img, known_face_locations=boxes)
    return encodings[0], len(encodings)

def compute_distance(encA, encB):
    return float(face_recognition.face_distance([encA], encB)[0])

def is_match(encA, encB, threshold=0.6):
    return compute_distance(encA, encB) <= threshold

def build_target_encodings(target_paths, model="hog", log=lambda m: None):   
    """Load all target faces into a list of embeddings."""
    encs = []
    for p in target_paths:
        try:
            enc, count = load_face_embedding(p, model=model)
            if enc is None:
                log(f"[FaceMatch] No face found in target image: {p} ({count} faces)")
            else:
                log(f"[FaceMatch] Loaded target face: {p}")
                encs.append(enc)
        except Exception as e:
            log(f"[FaceMatch] Error loading target {p}: {e}")
    return encs
    
def scan_and_copy_matches(target_encs, source_folder, matched_folder,
                          threshold=0.6, model="hog", log=lambda m: None, progress_callback=None):
    """Scan folder for images containing any of target faces. Copy matches to matched_folder."""
    # Gather all image files
    image_files = []
    for root, dirs, files in os.walk(source_folder):
        for f in files:
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".webp:", ".tiff")):
                image_files.append(os.path.join(root, f))

    total_files = len(image_files)
    if total_files == 0:
        log("[FaceMatch] No imnages found in source older.")
        return

    for idx, img_path in enumerate(img_path):
        try:
            img = face_recognition.load_image_file(img_path)
            boxes = face_recognition.face_locations(img, model=model)
            encs = face_recognition.face_encodings(img, known_face_locations=boxes)

            for e in encs:
                for t in target_encs:
                    if is_match(t, e, threshold):
                        # Build safe destination name (prevent overwritting)
                        base = os.path.splitext(os.path.basename(img_path))[0]
                        ext = os.path.splitext(img_path)[1]
                        dst = os.path.join(matched_folder, base + ext)

                        counter = 1
                        while os.path.exists(dst):
                            dst = os.path.join(matched_folder, f"{base}_{counter}{ext}")
                            counter += 1

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
            pct = max(0.0, min(100.0, pct))
            progress_callback(pct)

    log("[FaceMatch] Completed scanning.")
    