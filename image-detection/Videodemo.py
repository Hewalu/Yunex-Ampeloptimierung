import cv2
import time
import numpy as np
from ultralytics import YOLO
import tkinter as tk
from tkinter import filedialog
import sys

# Konfiguration
DEBOUNCE_TIME = 0.25  # Reduziert auf 0.25 Sekunden


class CountSmoother:
    def __init__(self):
        self.display_count = 0
        self.pending_count = 0
        self.pending_start_time = time.time()

    def update(self, raw_count):
        # Wenn sich der rohe Wert ändert, setze den Timer zurück
        if raw_count != self.pending_count:
            self.pending_count = raw_count
            self.pending_start_time = time.time()
        else:
            # Wenn der Wert stabil ist, prüfe wie lange schon
            if time.time() - self.pending_start_time >= DEBOUNCE_TIME:
                self.display_count = self.pending_count

        return self.display_count


class SpeedEstimator:
    def __init__(self):
        # Dictionary to store tracking history: id -> {positions: [(ts, x, y, h)], last_speed: float}
        self.tracks = {}
        # Parameters
        self.history_duration = 1.0  # Keep 1 second of history
        self.speed_smooth_factor = 0.7  # EMA factor for speed

    def update(self, results):
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
                    
                    # Track Y-movement for direction
                    # cy > y0 -> Moving Down -> Incoming
                    # cy < y0 -> Moving Up -> Outgoing
                    
                    # Estimate scale: Assume average person is 1.7m tall
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
                 if direction == "WAITING":
                     direction = "UNKNOWN" # Reset if started moving
                 
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
        w = x2 - x1
        h = y2 - y1

        # Check if we need transparency
        if alpha < 1.0 and thickness == -1:
            overlay = img.copy()
            # Draw standard rounded rect on overlay (Mockup)
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
            # Inner rects
            cv2.rectangle(img, (x1 + radius, y1), (x2 - radius, y2), color, thickness)
            cv2.rectangle(img, (x1, y1 + radius), (x2, y2 - radius), color, thickness)
            pass

    @staticmethod
    def draw_glass_panel(img, x, y, w, h, color=Colors.PANEL_BG, alpha=0.85):
        """Draws a modern glass-morphism style panel."""
        UIUtils.draw_rounded_rect(img, (x, y), (x + w, y + h), color, radius=15, thickness=-1, alpha=alpha)
        # Add a subtle border
        UIUtils.draw_rounded_rect(img, (x, y), (x + w, y + h), (60, 60, 60), radius=15, thickness=1)

    @staticmethod
    def draw_text(img, text, pos, font_scale=0.8, color=Colors.TEXT_WHITE, thickness=1, align="left"):
        font = cv2.FONT_HERSHEY_SIMPLEX
        (w, h), baseline = cv2.getTextSize(text, font, font_scale, thickness)
        x, y = pos

        if align == "center":
            x -= w // 2
        elif align == "right":
            x -= w

        cv2.putText(img, text, (x, y), font, font_scale, color, thickness, cv2.LINE_AA)
        return w, h

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


def draw_interface(frame, person_count, width=1920, height=1080):
    # 1. Background
    canvas = np.full((height, width, 3), Colors.BG_DARK, dtype=np.uint8)

    # 2. Left Side: Camera Feed (Modern Frame)
    # Calculate margins
    margin = 40
    feed_w = int(width * 0.65)
    feed_h = int(height - 2 * margin)

    # Resize Grid
    h, w = frame.shape[:2]
    # Handle case where frame is empty or size 0
    if w == 0 or h == 0:
        return canvas

    scale = min(feed_w / w, feed_h / h)
    new_w = int(w * scale)
    new_h = int(h * scale)
    resized_frame = cv2.resize(frame, (new_w, new_h))

    feed_x = margin
    feed_y = (height - new_h) // 2

    # Draw Shadows/Glow (Simulated by multiple rectangles opacity descending? Too slow in python)
    # Just draw a nice border and glass panel behind
    UIUtils.draw_glass_panel(canvas, feed_x - 10, feed_y - 10, new_w + 20, new_h + 20, alpha=0.3)
    canvas[feed_y:feed_y+new_h, feed_x:feed_x+new_w] = resized_frame
    cv2.rectangle(canvas, (feed_x, feed_y), (feed_x+new_w, feed_y+new_h), (50, 50, 50), 1)

    # 3. Right Side: Dashboard
    dash_x = feed_x + new_w + margin
    dash_w = width - dash_x - margin
    dash_h = height - 2 * margin

    # --- Status Header (Time, FPS placeholder) ---
    local_time = time.strftime("%H:%M:%S")
    UIUtils.draw_text(canvas, f"DEMO MODE | {local_time}", (dash_x, margin + 30), 0.6, Colors.TEXT_GRAY)

    # --- Person Counter Panel ---
    # Center X of dashboard
    dash_cx = dash_x + dash_w // 2

    panel_y = margin + 100
    panel_h = 300
    UIUtils.draw_glass_panel(canvas, dash_x, panel_y, dash_w, panel_h)

    UIUtils.draw_text(canvas, "DETECTED PERSONS", (dash_cx, panel_y + 50), 0.7, Colors.TEXT_GRAY, 1, align="center")
    UIUtils.draw_text(canvas, str(person_count), (dash_cx, panel_y + 160), 5.0, Colors.ACCENT_BLUE, 10, align="center")

    # Visual Indicator Bars (Fake Graph)
    bar_w = 40
    bar_gap = 10
    start_bar_x = dash_cx - (5 * (bar_w + bar_gap)) // 2

    for i in range(5):
        # Height depends on if person count > threshold
        is_active = person_count > (i * 2)
        bh = 30 + i * 10
        bx = start_bar_x + i * (bar_w + bar_gap)
        by = panel_y + 240
        b_color = Colors.ACCENT_BLUE if is_active else (60, 60, 60)

        cv2.rectangle(canvas, (bx, by), (bx + bar_w, by - bh), b_color, -1)

    return canvas


def get_track_color(track_id):
    """Generates a consistent color for a track ID."""
    np.random.seed(int(track_id))
    color = np.random.randint(0, 255, 3).tolist()
    return tuple(color)


def select_video_file():
    """Opens a file dialog to select a video file."""
    root = tk.Tk()
    root.withdraw() # Hide the main window
    
    file_path = filedialog.askopenfilename(
        title="Wähle eine Videodatei aus",
        filetypes=[
            ("Video files", "*.mp4 *.avi *.mov *.mkv"),
            ("All files", "*.*")
        ]
    )
    
    return file_path


def main():
    print("Starte Demo-Modus...")
    
    video_path = select_video_file()
    
    if not video_path:
        print("Kein Video ausgewählt. Beende Programm.")
        return

    print(f"Video ausgewählt: {video_path}")

    # Lade das YOLOv11 Nano Segmentation Modell
    print("Lade Modell (YOLOv11n-seg)...")
    try:
        model = YOLO("yolo11n-seg.pt")
    except Exception as e:
        print(f"Fehler beim Laden des Modells: {e}")
        return

    # Initialisiere Logik-Klassen
    smoother = CountSmoother()
    speed_estimator = SpeedEstimator()

    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        print(f"Fehler: Konnte Video '{video_path}' nicht öffnen.")
        return

    # Fenster erstellen und auf Vollbild setzen
    window_name = "Personenerkennung Demo"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    print("Starte Videoanalyse.")
    print(" [q] Beenden")

    while True:
        success, frame = cap.read()
        if not success:
            print("Ende des Videos.")
            # Optional: Loop video
            # cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            # continue
            break

        # Führe YOLO Tracking auf dem Frame aus (aktiviere Masken)
        # Hinweis: retina_masks=True sorgt für bessere Maskenqualität, ist aber etwas langsamer.
        results = model.track(frame, classes=[0, 2], persist=True, verbose=False, retina_masks=True)

        # Clone frame for clean drawing
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
        speeds = speed_estimator.update(results)

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
                    style = "outward" # Corners point out
                elif direction == "OUTGOING":
                    dir_label = "| WEG"
                    style = "inward" # Corners point in
                elif direction == "WAITING":
                    dir_label = "| WARTET"
                    style = "inward" # Corners point in

                label = f"{speed:.1f} m/s {dir_label}"
                UIUtils.draw_hud_box(annotated_frame, box, color, label, category, style=style)

        # Zähle Personen (Rohdaten)
        # Nur Personen zählen (class 0)
        boxes_cls = results[0].boxes.cls.int().cpu().tolist()
        raw_count = boxes_cls.count(0)

        # Glätte den Wert (Debouncing)
        smooth_count = smoother.update(raw_count)

        # Erstelle das UI (ohne Ampel)
        ui_frame = draw_interface(annotated_frame, smooth_count)

        # Zeige das Bild an (Window config should handle resize)
        cv2.imshow(window_name, ui_frame)

        # Tastensteuerung
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        
        # Add slight delay if processing is too fast for playback visualization
        # time.sleep(0.01)

    # Ressourcen freigeben
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
