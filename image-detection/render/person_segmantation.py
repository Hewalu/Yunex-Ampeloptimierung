import cv2
import os
import time
import numpy as np
from ultralytics import YOLO

# --- KONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(os.path.dirname(BASE_DIR), "models")
MODEL_NAME = "yolo26x-seg.pt"

INPUT_ROOT = os.path.join(BASE_DIR, "input")
OUTPUT_ROOT = os.path.join(BASE_DIR, "output")

# Liste der zu verarbeitenden Videos (Dateinamen). Leer lassen für alle.
# Beispiel: TARGET_VIDEOS = ["video1.mp4", "test.mp4"]
TARGET_VIDEOS = ["big_group.mp4"]

# YOLO Model Configuration
CONF_THRESHOLD = 0.25
IOU_THRESHOLD = 0.5
CLASSES = [0, 2]  # Person (0) und Car (2)
PERSIST = True


class Colors:
    # Modern Color Palette
    BG_DARK = (18, 18, 18)        # #121212
    PANEL_BG = (30, 30, 30)       # #1E1E1E
    TEXT_WHITE = (240, 240, 240)  # #F0F0F0
    TEXT_GRAY = (176, 176, 176)   # #B0B0B0

    ACCENT_RED = (58, 69, 255)    # #FF453A (BGR)
    ACCENT_GREEN = (75, 215, 50)  # #32D74B (BGR)
    ACCENT_ORANGE = (10, 159, 255)  # FF9F0A (BGR)
    ACCENT_BLUE = (255, 132, 10)  # #0A84FF (BGR)


class UIUtils:
    @staticmethod
    def draw_rounded_rect(img, top_left, bottom_right, color, radius=10, thickness=-1, alpha=1.0):
        """Draws a rounded rectangle, optionally transparent."""
        x1, y1 = top_left
        x2, y2 = bottom_right

        # Check if we need transparency
        if alpha < 1.0 and thickness == -1:
            overlay = img.copy()
            # Inner rects
            cv2.rectangle(overlay, (x1 + radius, y1), (x2 - radius, y2), color, -1)
            cv2.rectangle(overlay, (x1, y1 + radius), (x2, y2 - radius), color, -1)
            # Corners
            cv2.circle(overlay, (x1 + radius, y1 + radius), radius, color, -1)
            cv2.circle(overlay, (x2 - radius, y1 + radius), radius, color, -1)
            cv2.circle(overlay, (x1 + radius, y2 - radius), radius, color, -1)
            cv2.circle(overlay, (x2 - radius, y2 - radius), radius, color, -1)

            cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)
        else:
            cv2.rectangle(img, (x1 + radius, y1), (x2 - radius, y2), color, thickness)
            cv2.rectangle(img, (x1, y1 + radius), (x2, y2 - radius), color, thickness)

    @staticmethod
    def draw_glass_panel(img, x, y, w, h, color=Colors.PANEL_BG, alpha=0.85):
        """Draws a modern glass-morphism style panel."""
        UIUtils.draw_rounded_rect(img, (x, y), (x + w, y + h), color, radius=15, thickness=-1, alpha=alpha)
        # Add a subtle border
        UIUtils.draw_rounded_rect(img, (x, y), (x + w, y + h), (60, 60, 60), radius=15, thickness=1)

    @staticmethod
    def draw_hud_box(img, box, color, label=None, sublabel=None, style="inward"):
        """Draws a tech/sci-fi style corner bracket box."""
        x1, y1, x2, y2 = map(int, box)
        w = x2 - x1
        h = y2 - y1
        line_len = min(w, h) // 4
        thickness = 2

        if style == "outward":
            # Corners pointing OUTWARDS
            # Top-Left
            cv2.line(img, (x1, y1), (x1 - line_len, y1), color, thickness)
            cv2.line(img, (x1, y1), (x1, y1 - line_len), color, thickness)
            # Top-Right
            cv2.line(img, (x2, y1), (x2 + line_len, y1), color, thickness)
            cv2.line(img, (x2, y1), (x2, y1 - line_len), color, thickness)
            # Bottom-Left
            cv2.line(img, (x1, y2), (x1 - line_len, y2), color, thickness)
            cv2.line(img, (x1, y2), (x1, y2 + line_len), color, thickness)
            # Bottom-Right
            cv2.line(img, (x2, y2), (x2 + line_len, y2), color, thickness)
            cv2.line(img, (x2, y2), (x2, y2 + line_len), color, thickness)
        else:
            # Corners pointing INWARDS (Default)
            # Top-Left
            cv2.line(img, (x1, y1), (x1 + line_len, y1), color, thickness)
            cv2.line(img, (x1, y1), (x1, y1 + line_len), color, thickness)
            # Top-Right
            cv2.line(img, (x2, y1), (x2 - line_len, y1), color, thickness)
            cv2.line(img, (x2, y1), (x2, y1 + line_len), color, thickness)
            # Bottom-Left
            cv2.line(img, (x1, y2), (x1 + line_len, y2), color, thickness)
            cv2.line(img, (x1, y2), (x1, y2 - line_len), color, thickness)
            # Bottom-Right
            cv2.line(img, (x2, y2), (x2 - line_len, y2), color, thickness)
            cv2.line(img, (x2, y2), (x2, y2 - line_len), color, thickness)

        # Label with glass background
        if label:
            # Adjust label width based on content
            font = cv2.FONT_HERSHEY_SIMPLEX
            (lw, lh), _ = cv2.getTextSize(label, font, 0.6, 1)
            panel_w = max(140, lw + 20)

            UIUtils.draw_glass_panel(img, x1, y1 - 35, panel_w, 30, color=(0, 0, 0), alpha=0.6)
            cv2.putText(img, label, (x1 + 10, y1 - 12), font, 0.6, Colors.TEXT_WHITE, 1, cv2.LINE_AA)
            if sublabel:
                cv2.putText(img, sublabel, (x1 + 10, y1 + 15), font, 0.4, Colors.TEXT_GRAY, 1, cv2.LINE_AA)


class SpeedEstimator:
    def __init__(self):
        # Dictionary to store tracking history: id -> {positions: [(ts, x, y, h)], last_speed: float}
        self.tracks = {}
        # Parameters
        # history_duration bestimmt, wie lange die Pfade (Trails) sind.
        self.history_duration = 3.0  # Erhöht für längere Trails
        self.speed_smooth_factor = 0.7  # EMA factor for speed

    def update(self, results, current_time=None):
        if current_time is None:
            current_time = time.time()

        active_speeds = {}  # id -> {speed: float, category: str, direction: str, box: [x1, y1, x2, y2]}

        if not results or not results[0].boxes.id is not None:
            return active_speeds

        # Extract data from YOLO results
        track_ids = results[0].boxes.id.int().cpu().tolist()
        boxes = results[0].boxes.xyxy.cpu().tolist()
        classes = results[0].boxes.cls.int().cpu().tolist()

        for track_id, box, cls_id in zip(track_ids, boxes, classes):
            x1, y1, x2, y2 = box
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
            h = y2 - y1

            if track_id not in self.tracks:
                self.tracks[track_id] = {
                    'positions': [],
                    'last_speed': 0.0,
                    'last_direction': "UNKNOWN"
                }

            # Add current position
            track_data = self.tracks[track_id]
            track_data['positions'].append((current_time, cx, cy, h))

            # Cleanup old positions
            track_data['positions'] = [p for p in track_data['positions'] if current_time - p[0] < self.history_duration]

            # Calculate speed and direction
            speed = 0.0
            direction = track_data.get('last_direction', "UNKNOWN")

            positions = track_data['positions']
            if len(positions) > 1:
                # Compare current with oldest in history (within window) for stability
                # Using the oldest available point gives a smoother average over the window
                t0, x0, y0, h0 = positions[0]
                dt = current_time - t0

                if dt > 0.1:  # Only calculate if we have a little bit of time passed
                    dist_pixels = np.sqrt((cx - x0)**2 + (cy - y0)**2)

                    # Direction Calculation (Y-axis movement)
                    # Y increases downwards.
                    # cy > y0 -> Moving Down -> Incoming (Top of screen to Bottom)
                    # cy < y0 -> Moving Up -> Outgoing (Bottom of screen to Top)
                    # dy = cy - y0
                    # if abs(dy) > 10: # Threshold to ignore jitter
                    #     if dy > 0:
                    #         direction = "INCOMING"
                    #     else:
                    #         direction = "OUTGOING"

                    # track_data['last_direction'] = direction

                    # Estimate scale: Assume average person is 1.7m tall
                    # pixels_per_meter = height_in_pixels / 1.7
                    avg_h = (h + h0) / 2
                    if avg_h > 0:
                        pixels_per_meter = avg_h / 1.7
                        dist_meters = dist_pixels / pixels_per_meter
                        raw_speed = dist_meters / dt

                        # Apply smoothing
                        speed = (self.speed_smooth_factor * raw_speed) + \
                                ((1 - self.speed_smooth_factor) * track_data['last_speed'])

            # Determine Direction based on Speed and Movement
            if speed < 0.25:
                # If speed is very low, assume waiting
                direction = "WAITING"
            else:
                # Only update direction if moving fast enough
                if direction == "WAITING":
                    direction = "UNKNOWN"  # Reset if started moving

                # Recalculate or use dy from above if available?
                # To be clean, we should recalc dy here or use movement
                if len(positions) > 1:
                    t0, x0, y0, h0 = positions[0]
                    dy = cy - y0
                    if abs(dy) > 10:
                        if dy > 0:
                            direction = "INCOMING"
                        else:
                            direction = "OUTGOING"

            track_data['last_direction'] = direction
            track_data['last_speed'] = speed

            # Categorize Speed
            category = "LOW"
            if speed > 1.65:
                category = "HIGH"
            elif speed > 1.1:
                category = "MEDIUM"

            active_speeds[track_id] = {
                'speed': speed,
                'category': category,
                'direction': direction,
                'box': box,
                'class_id': cls_id
            }

        return active_speeds


def get_track_color(track_id):
    """Generates a consistent color for a track ID."""
    np.random.seed(int(track_id))
    color = np.random.randint(0, 255, 3).tolist()
    return tuple(color)


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

    # Fallback: Wenn Modell nicht lokal unter models/ gefunden wird, lass YOLO es laden/downloaden
    if os.path.exists(model_path):
        model = YOLO(model_path)
    else:
        print(f"Modell {model_path} nicht gefunden, lade via Ultralytics (automatischer Download)...")
        model = YOLO(MODEL_NAME)

    cap = cv2.VideoCapture(video_path)
    speed_estimator = SpeedEstimator()

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    out = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*'mp4v'), int(fps), (width, height))

    print(f"Verarbeite Video: {video_path}")

    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            break

        # Calculate video timestamp in seconds for speed estimation
        current_idx = cap.get(cv2.CAP_PROP_POS_FRAMES)
        timestamp = current_idx / fps if fps > 0 else 0

        # YOLO Tracking
        results = model.track(
            frame,
            persist=PERSIST,
            conf=CONF_THRESHOLD,
            iou=IOU_THRESHOLD,
            classes=CLASSES,
            verbose=False,
            retina_masks=True  # Hochauflösende Masken
        )

        # Frame kopieren für Annotationen
        annotated_frame = frame.copy()

        # 1. Zeichne Segmentation Masks (Hintergrund) bevor die Boxen kommen
        if results[0].boxes.id is not None and results[0].masks is not None:
            track_ids = results[0].boxes.id.int().cpu().tolist()

            # Die Masken-Konturen abrufen (Liste von Arrays mit Koordinaten)
            # Verwende enumerate, da masks und boxes korrespondieren
            for i, track_id in enumerate(track_ids):
                try:
                    # Zufällige, aber konsistente Farbe für jede Person
                    color = get_track_color(track_id)

                    # Kontur abrufen
                    seg = results[0].masks.xy[i]

                    if len(seg) > 0:
                        seg = seg.astype(np.int32)

                        # Overlay erstellen
                        overlay = annotated_frame.copy()
                        cv2.drawContours(overlay, [seg], -1, color, -1)  # Ausgefüllt

                        # Transparenz anwenden (z.B. 40% Deckkraft)
                        alpha = 0.4
                        cv2.addWeighted(overlay, alpha, annotated_frame, 1 - alpha, 0, annotated_frame)

                        # Optionale Outline um die Fläche (deckend)
                        cv2.drawContours(annotated_frame, [seg], -1, color, 2)

                except Exception:
                    pass

        # Update Speed Estimation
        speeds = speed_estimator.update(results, timestamp)

        # 1.5. Zeichne Motion Trails (Pfade)
        # Wir nutzen die Historie aus dem SpeedEstimator
        for track_id, track_data in speed_estimator.tracks.items():
            # Prüfe, ob Track aktuell noch aktiv ist (optional, oder wir zeichnen auch "Geisterpfade" kurz nach)
            # Hier zeichnen wir einfach alles was noch im Speicher ist (wird eh nach history_duration gelöscht)
            positions = track_data['positions']
            if len(positions) > 2:
                # Extrahiere Punkte (cx, cy)
                points = []
                for _, cx, cy, _ in positions:
                    points.append([int(cx), int(cy)])

                points = np.array(points, dtype=np.int32).reshape((-1, 1, 2))

                color = get_track_color(track_id)
                # Zeichne Polyline
                cv2.polylines(annotated_frame, [points], isClosed=False, color=color, thickness=2)

                # Optional: Punkte an den Positionen zeichnen für "Tech-Look"
                # for p in points:
                #    cv2.circle(annotated_frame, tuple(p[0]), 2, color, -1)

        # 2. Zeichne HUD Overlays (Vordergrund/Ecken)
        for track_id, data in speeds.items():
            speed = data['speed']
            category = data['category']
            direction = data.get('direction', 'UNKNOWN')
            box = data['box']
            cls_id = data.get('class_id', 0)
            x1, y1, x2, y2 = map(int, box)

            if cls_id == 2:  # Car / Auto
                # Nur fahrende Autos markieren: speed > 0.5 (als Schwellenwert)
                if speed > 0.5:
                    color = Colors.ACCENT_RED
                    label = "Auto"
                    sublabel = f"{speed:.1f} m/s"
                    UIUtils.draw_hud_box(annotated_frame, box, color, label, sublabel, style="outward")
            else:
                # Person logic
                # Farbe je nach Kategorie
                if category == "HIGH":
                    color = Colors.ACCENT_RED
                elif category == "MEDIUM":
                    color = Colors.ACCENT_ORANGE
                else:  # LOW
                    color = Colors.ACCENT_GREEN

                # Determine Label and Style
                dir_label = ""
                style = "inward"

                if direction == "INCOMING":
                    dir_label = "| HIN"
                    style = "outward"  # Corners point out
                elif direction == "OUTGOING":
                    dir_label = "| WEG"
                    style = "inward"  # Corners point in
                elif direction == "WAITING":
                    dir_label = "| WARTET"
                    style = "inward"  # Corners point in

                label = f"{speed:.1f} m/s {dir_label}"
                UIUtils.draw_hud_box(annotated_frame, box, color, label, category, style=style)

        out.write(annotated_frame)

    cap.release()
    out.release()
    print(f"Fertig! Gespeichert unter: {output_path}")


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
                if file.lower().endswith(('.mp4')):
                    # Wenn TARGET_VIDEOS definiert ist, nur diese Videos verarbeiten
                    if TARGET_VIDEOS and file not in TARGET_VIDEOS:
                        continue

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
