import cv2
import os
from ultralytics import YOLO
from collections import defaultdict
import numpy as np

# --- KONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Gehe ein Verzeichnis hoch (zu image-detection) und dann in 'models'
MODELS_DIR = os.path.join(os.path.dirname(BASE_DIR), "models")

INPUT_ROOT = os.path.join(BASE_DIR, "input")
OUTPUT_ROOT = os.path.join(BASE_DIR, "output")

# YOLO Model Configuration
MODEL_NAME = "yolo11x.pt"
CONF_THRESHOLD = 0.25   # Mindest-Wahrscheinlichkeit (0.0 - 1.0)
IOU_THRESHOLD = 0.5     # Overlap Threshold für NMS (0.0 - 1.0)
CLASSES = [0]           # Klassen-Filter: 0 = Person. None für alle Klassen.
PERSIST = True          # IDs über Frames behalten

TRACK_HISTORY = defaultdict(lambda: [])
MAX_TRAIL_LENGTH = 30
# ---------------------


def get_next_output_folder(base_output_dir):
    """Ermittelt den nächsten numerischen Ordner (1, 2, 3...) im Output-Verzeichnis mit Modell-Suffix."""
    # .pt Endung entfernen für schöneren Ordnernamen
    clean_model_name = MODEL_NAME.replace(".pt", "")

    if not os.path.exists(base_output_dir):
        os.makedirs(base_output_dir)
        folder_name = f"1_{clean_model_name}"
        new_path = os.path.join(base_output_dir, folder_name)
        os.makedirs(new_path)
        return new_path

    # Suche alle Ordner und versuche die Nummer am Anfang zu parsen
    max_num = 0
    for d in os.listdir(base_output_dir):
        if not os.path.isdir(os.path.join(base_output_dir, d)):
            continue

        # Versuche Zahl am Anfang zu finden (z.B. "1" oder "1_yolo11x")
        try:
            # Split bei '_' und nimm den ersten Teil
            num_part = d.split('_')[0]
            if num_part.isdigit():
                num = int(num_part)
                if num > max_num:
                    max_num = num
        except ValueError:
            continue

    next_num = max_num + 1

    # Ordnername: "Nummer_Modellname"
    new_folder_name = f"{next_num}_{clean_model_name}"
    new_folder = os.path.join(base_output_dir, new_folder_name)
    os.makedirs(new_folder)
    return new_folder


def process_video(video_path, output_folder):
    filename = os.path.basename(video_path)
    # Output-Dateiname zusammenbauen
    output_path = os.path.join(output_folder, "tracked_" + filename)

    print(f"Lade Modell: {MODEL_NAME} für {filename}...")
    model_path = os.path.join(MODELS_DIR, MODEL_NAME)
    model = YOLO(model_path)

    cap = cv2.VideoCapture(video_path)

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv2.CAP_PROP_FPS))

    out = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (width, height))

    print(f"Verarbeite Video: {video_path}")

    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            break

        # YOLO Tracking mit Parametern aus der Konfiguration
        results = model.track(
            frame,
            persist=PERSIST,
            conf=CONF_THRESHOLD,
            iou=IOU_THRESHOLD,
            classes=CLASSES,
            verbose=False
        )

        if results[0].boxes.id is not None:
            boxes = results[0].boxes.xywh.cpu()
            track_ids = results[0].boxes.id.int().cpu().tolist()

            annotated_frame = results[0].plot()

            for box, track_id in zip(boxes, track_ids):
                x, y, w, h = box
                center = (float(x), float(y))

                track = TRACK_HISTORY[track_id]
                track.append(center)
                if len(track) > MAX_TRAIL_LENGTH:
                    track.pop(0)

                points = np.hstack(track).astype(np.int32).reshape((-1, 1, 2))
                cv2.polylines(annotated_frame, [points], isClosed=False, color=(0, 255, 255), thickness=4)
        else:
            annotated_frame = frame

        out.write(annotated_frame)

    cap.release()
    out.release()
    print(f"Fertig! Gespeichert unter: {output_path}")

    TRACK_HISTORY.clear()


# --- MAIN ---
if __name__ == "__main__":
    # Nächsten Output-Ordner bestimmen (1, 2, 3...)
    current_out_dir = get_next_output_folder(OUTPUT_ROOT)
    print(f"Ergebnisse werden gespeichert in: {current_out_dir}")

    # Rekursiv nach Videos suchen oder spezifisch in 'new' und 'shaky'
    # Hier suchen wir rekursiv im gesamten INPUT_ROOT (umfasst new und shaky)
    video_files = []

    if os.path.exists(INPUT_ROOT):
        for root, dirs, files in os.walk(INPUT_ROOT):
            for file in files:
                # Unterscheidung auf .mov case-insensitive
                if file.lower().endswith(('.mov', '.mp4', '.avi', '.mkv')):
                    full_path = os.path.join(root, file)
                    video_files.append(full_path)
    else:
        print(f"Input Ordner nicht gefunden: {INPUT_ROOT}")

    if not video_files:
        print(f"Keine Videos in '{INPUT_ROOT}' (Unterordner eingeschlossen) gefunden.")
    else:
        print(f"{len(video_files)} Videos gefunden.")
        for video in video_files:
            try:
                process_video(video, current_out_dir)
            except Exception as e:
                print(f"Fehler bei {video}: {e}")
