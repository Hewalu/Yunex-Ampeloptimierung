"""
Integrierte Anwendung: Kamera-Personenerkennung + Ampel-Interface + ESP-Steuerung
==================================================================================
Startet ein skalierbares Fenster mit:
  - LINKS:  Live-Kamerabild (iMac-Kamera) mit YOLO-Personenerkennung & Segmentierung
  - RECHTS: Ampel-Visualisierung (Gehäuse, Ampelmännchen, LED-Ring, Personen-Icons)
  - UNTEN:  Status-Leiste mit Zustand, Personenzählung und Tastenkürzel

Die Personenanzahl aus der Kamera steuert automatisch die Ampellogik.
Zusätzlich können HAL-Sensoren und Buttons am physischen ESP-Modell genutzt werden.

Fenster: Skalierbar und verschiebbar. [F] für Vollbild-Toggle.

Start:  python integrated_main.py
        python integrated_main.py --source 1          (andere Kamera)
        python integrated_main.py --no-esp             (ohne ESP)
        python integrated_main.py --windowed           (feste Größe 1600×900)
"""

import pygame
import pygame.freetype
from pygame import gfxdraw
import cv2
import numpy as np
import math
import sys
import os
import time
import threading
import argparse
import serial.tools.list_ports

# === Pfade setzen (PyInstaller-kompatibel) ===
# Im gebündelten App-Modus liegen Ressourcen im _MEIPASS-Verzeichnis
if getattr(sys, 'frozen', False):
    # Gebündelte App (PyInstaller)
    BASE_DIR = sys._MEIPASS
    # Ultralytics braucht ein beschreibbares Verzeichnis für Config/Cache
    _user_data = os.path.join(os.path.expanduser('~'), '.trafficowl')
    os.makedirs(_user_data, exist_ok=True)
    os.environ['YOLO_CONFIG_DIR'] = _user_data
    os.environ['ULTRALYTICS_CONFIG_DIR'] = _user_data
else:
    # Normaler Python-Aufruf
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SCRIPT_DIR = BASE_DIR
INTERFACE_DIR = os.path.join(BASE_DIR, "Interface")
DETECTION_DIR = os.path.join(BASE_DIR, "image-detection")
MODELS_DIR = os.path.join(DETECTION_DIR, "models")
ASSET_DIR = os.path.join(INTERFACE_DIR, "assets")

# Interface-Verzeichnis zum Python-Pfad hinzufügen (für esp_control Import)
sys.path.insert(0, INTERFACE_DIR)

# === Hardware-Module laden ===
try:
    from esp_control import ESPController
    ESP_AVAILABLE = True
except ImportError:
    ESP_AVAILABLE = False
    print("[SYSTEM] esp_control.py nicht gefunden. ESP deaktiviert.")

try:
    from traffic_logic import TrafficLightLogic
    LOGIC_AVAILABLE = True
except ImportError:
    LOGIC_AVAILABLE = False

# === YOLO laden ===
YOLO_AVAILABLE = False
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    print("[SYSTEM] ultralytics nicht installiert. Kamera-Erkennung deaktiviert.")

# ==========================================
#      KONFIGURATION
# ==========================================

MODEL_NAME = "yolo26n-seg.pt"
DEBOUNCE_TIME = 0.25

# --- Ampel-Zeiten ---
SCALE_FACTOR = 0.3
MAX_PERSON_CAP = 8
MAX_VISUAL_PERSONS = 8
ADD_LEDS_PER_PERSON = 1
CROWD_BONUS_FACTOR = 0.3

BASE_LEDS_GREEN = 25
VISUAL_LED_COUNT = 25
TOTAL_LEDS_RED = 25
MAX_LEDS_LIMIT = 30

SECONDS_PER_LED_RED = 0.40
SECONDS_PER_LED_GREEN = 0.66
SECONDS_PER_LED_GREEN_SLOW = 1.0

TIME_SAFETY_PRE_GREEN = 3000
TIME_CLEARANCE = 6000
TIME_CAR_YELLOW = 3000
TIME_CAR_RED_YELLOW = 1500

TIME_TRAM_PRE_GREEN = 5000
TIME_TRAM_GREEN_DURATION = 25000
TIME_TRAM_YELLOW = 3000
TIME_TRAM_SAFETY = 2000

DURATION_RED_BASE_MS = int(TOTAL_LEDS_RED * SECONDS_PER_LED_RED * 1000)

# --- Optik ---
TIMER_FONT_SIZE = 280
ORIGINAL_LED_RADIUS = 235
ORIGINAL_DOT_SIZE = 20
WAITING_ICON_SCALE = 0.22

OFFSET_ROT_Y = -230
OFFSET_GRUEN_Y = 230
OFFSET_RING_Y = -2
OFFSET_TRAM_Y = -2

COLOR_LED_ON = (255, 255, 255)
COLOR_LED_OFF = (40, 40, 40)
COLOR_CLEARANCE = (255, 50, 50)
COLOR_WALKER = (255, 255, 255)

# --- Zustände ---
STATE_IDLE = "IDLE"
STATE_RED = "RED"
STATE_SAFETY_1 = "SAFETY_1"
STATE_GREEN = "GREEN"
STATE_CLEARANCE = "CLEARANCE"
STATE_TRAM = "TRAM"


def debug_log(message):
    print(f"[DEBUG] {message}", flush=True)


def get_auto_port():
    try:
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            if "CP210" in p.description or "CH340" in p.description or "USB Serial" in p.description:
                return p.device
        if ports:
            return ports[0].device
    except Exception:
        pass
    return "/dev/tty.usbserial-0001"


# ==========================================
#      YOLO / KAMERA THREAD
# ==========================================

class CountSmoother:
    """Debounce für die Personenanzahl."""
    def __init__(self):
        self.display_count = 0
        self.pending_count = 0
        self.pending_start_time = time.time()

    def update(self, raw_count):
        if raw_count != self.pending_count:
            self.pending_count = raw_count
            self.pending_start_time = time.time()
        else:
            if time.time() - self.pending_start_time >= DEBOUNCE_TIME:
                self.display_count = self.pending_count
        return self.display_count


class CameraDetector:
    """
    Führt YOLO-Personenerkennung in einem eigenen Thread aus.
    Stellt das annotierte Frame und die Personenanzahl bereit.
    """

    def __init__(self, source=0, model_name=MODEL_NAME):
        self.source = source
        self.model_name = model_name
        self.model = None
        self.cap = None

        self.lock = threading.Lock()
        self._frame = None           # Aktuelles annotiertes Frame (BGR, numpy)
        self._person_count = 0       # Geglättete Personenanzahl
        self._raw_count = 0
        self._running = False
        self._thread = None

        self.smoother = CountSmoother()

    def start(self):
        """
        Startet Kamera und YOLO.
        WICHTIG: Kamera wird im Main-Thread geöffnet (macOS-Anforderung
        für gebündelte .app – Kamera-Zugriff muss vom Main-Thread kommen).
        Nur die YOLO-Verarbeitung läuft im Hintergrund-Thread.
        """
        if not YOLO_AVAILABLE:
            debug_log("YOLO nicht verfügbar - Kamera-Thread wird nicht gestartet.")
            return False

        model_path = os.path.join(MODELS_DIR, self.model_name)
        if not os.path.exists(model_path):
            debug_log(f"Modell nicht gefunden: {model_path}")
            debug_log(f"  (MODELS_DIR = {MODELS_DIR})")
            debug_log(f"  (BASE_DIR = {BASE_DIR})")
            # Verzeichnis-Inhalt loggen zum Debuggen
            if os.path.exists(MODELS_DIR):
                debug_log(f"  Inhalt von MODELS_DIR: {os.listdir(MODELS_DIR)}")
            else:
                debug_log(f"  MODELS_DIR existiert nicht!")
            return False

        debug_log(f"Lade YOLO-Modell: {self.model_name}...")
        try:
            self.model = YOLO(model_path)
            debug_log("YOLO-Modell erfolgreich geladen.")
        except Exception as e:
            debug_log(f"YOLO-Modell konnte nicht geladen werden: {e}")
            return False

        # Kamera im Main-Thread öffnen (macOS erfordert das bei .app-Bundles)
        debug_log(f"Öffne Kamera {self.source} (Main-Thread)...")
        self.cap = cv2.VideoCapture(self.source)
        if not self.cap.isOpened():
            debug_log(f"Kamera {self.source} konnte nicht geöffnet werden.")
            return False

        # Test-Frame lesen um sicherzustellen dass die Kamera wirklich liefert
        test_ok, test_frame = self.cap.read()
        if not test_ok or test_frame is None:
            debug_log(f"Kamera {self.source} geöffnet, aber liefert keine Frames.")
            return False

        debug_log(f"Kamera {self.source} geöffnet und liefert Frames ({test_frame.shape}).")
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def _get_track_color(self, track_id):
        np.random.seed(int(track_id))
        color = np.random.randint(0, 255, 3).tolist()
        return tuple(color)

    def _run(self):
        """Haupt-Loop des Kamera-Threads."""
        debug_log("Kamera-Thread gestartet.")
        consecutive_failures = 0
        try:
          while self._running:
            success, frame = self.cap.read()
            if not success:
                consecutive_failures += 1
                if consecutive_failures > 100:
                    debug_log("Kamera liefert dauerhaft keine Frames – Thread wird beendet.")
                    break
                time.sleep(0.05)
                continue
            consecutive_failures = 0

            # Bild spiegeln (Spiegel-Modus für Ausstellung)
            frame = cv2.flip(frame, 1)

            # YOLO Tracking mit Segmentierung
            results = self.model.track(
                frame, classes=[0], persist=True,
                verbose=False, retina_masks=True
            )

            annotated = frame.copy()
            h_frame, w_frame = annotated.shape[:2]

            # Segmentierungs-Masken zeichnen
            if results[0].boxes.id is not None and results[0].masks is not None:
                track_ids = results[0].boxes.id.int().cpu().tolist()

                for i, track_id in enumerate(track_ids):
                    try:
                        color = self._get_track_color(track_id)
                        seg = results[0].masks.xy[i]
                        if len(seg) > 0:
                            seg = seg.astype(np.int32)
                            overlay = annotated.copy()
                            cv2.drawContours(overlay, [seg], -1, color, -1)
                            cv2.addWeighted(overlay, 0.35, annotated, 0.65, 0, annotated)
                            cv2.drawContours(annotated, [seg], -1, color, 2)
                    except Exception:
                        pass

                # HUD-Boxen zeichnen (modernes Design)
                boxes = results[0].boxes.xyxy.cpu().tolist()
                for track_id, box in zip(track_ids, boxes):
                    x1, y1, x2, y2 = map(int, box)
                    color = self._get_track_color(track_id)
                    # Farbe aufhellen für bessere Sichtbarkeit
                    bright = tuple(min(255, c + 40) for c in color)
                    w = x2 - x1
                    h = y2 - y1
                    line_len = min(w, h) // 4
                    thickness = 2

                    # Corner brackets (sci-fi style)
                    cv2.line(annotated, (x1, y1), (x1 + line_len, y1), bright, thickness, cv2.LINE_AA)
                    cv2.line(annotated, (x1, y1), (x1, y1 + line_len), bright, thickness, cv2.LINE_AA)
                    cv2.line(annotated, (x2, y1), (x2 - line_len, y1), bright, thickness, cv2.LINE_AA)
                    cv2.line(annotated, (x2, y1), (x2, y1 + line_len), bright, thickness, cv2.LINE_AA)
                    cv2.line(annotated, (x1, y2), (x1 + line_len, y2), bright, thickness, cv2.LINE_AA)
                    cv2.line(annotated, (x1, y2), (x1, y2 - line_len), bright, thickness, cv2.LINE_AA)
                    cv2.line(annotated, (x2, y2), (x2 - line_len, y2), bright, thickness, cv2.LINE_AA)
                    cv2.line(annotated, (x2, y2), (x2, y2 - line_len), bright, thickness, cv2.LINE_AA)

                    # Label mit abgerundeter Glasoptik
                    label = f"Person #{track_id}"
                    font = cv2.FONT_HERSHEY_SIMPLEX
                    (lw, lh), baseline = cv2.getTextSize(label, font, 0.5, 1)
                    label_bg = annotated.copy()
                    cv2.rectangle(label_bg, (x1, y1 - 28), (x1 + lw + 14, y1 - 2), (20, 20, 20), -1)
                    cv2.addWeighted(label_bg, 0.7, annotated, 0.3, 0, annotated)
                    cv2.putText(annotated, label, (x1 + 7, y1 - 10), font, 0.5,
                                bright, 1, cv2.LINE_AA)

            # Personen zählen (nur class 0 = Person)
            boxes_cls = results[0].boxes.cls.int().cpu().tolist() if results[0].boxes.cls is not None else []
            raw_count = boxes_cls.count(0)
            smooth_count = self.smoother.update(raw_count)

            # ─── Dezentes Personen-HUD oben links ───
            hud_w, hud_h = 200, 50
            hud_overlay = annotated.copy()
            cv2.rectangle(hud_overlay, (12, 12), (12 + hud_w, 12 + hud_h), (15, 15, 15), -1)
            cv2.addWeighted(hud_overlay, 0.65, annotated, 0.35, 0, annotated)
            cv2.rectangle(annotated, (12, 12), (12 + hud_w, 12 + hud_h), (60, 60, 60), 1, cv2.LINE_AA)
            cv2.putText(annotated, f"Personen: {smooth_count}", (24, 46),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.85, (240, 240, 240), 2, cv2.LINE_AA)

            with self.lock:
                self._frame = annotated
                self._person_count = smooth_count
                self._raw_count = raw_count
        except Exception as e:
          debug_log(f"FEHLER im Kamera-Thread: {e}")
          import traceback
          debug_log(traceback.format_exc())
        debug_log("Kamera-Thread beendet.")

    def get_frame_and_count(self):
        """Thread-sicher: Frame und Personenanzahl abrufen."""
        with self.lock:
            return self._frame, self._person_count

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        if self.cap:
            self.cap.release()


# ==========================================
#      INTERFACE (Pygame Ampel-Visualisierung)
# ==========================================

class TrafficInterface:
    """Kapselt die gesamte Ampel-Visualisierung in Pygame."""

    def __init__(self):
        self.images = {}
        self.waiting_images = []
        self.game_font = None
        self.width = 0
        self.height = 0
        self.center_x = 0
        self.center_y = 0
        self.led_radius = 0
        self.dot_size_base = 0

    def load_images(self):
        """Lädt alle Assets und berechnet Dimensionen."""
        if not os.path.exists(ASSET_DIR):
            debug_log(f"Asset-Verzeichnis nicht gefunden: {ASSET_DIR}")
            sys.exit(1)

        self.images['housing'] = self._load_img('gehaeuse.png')
        self.images['red_on'] = self._load_img('mann_rot_an.png')
        self.images['red_off'] = self._load_img('mann_rot_aus.png')
        self.images['green_on'] = self._load_img('mann_gruen_an.png')
        self.images['green_off'] = self._load_img('mann_gruen_aus.png')
        self.images['tram'] = self._load_img('tram.png', scale=SCALE_FACTOR * 0.7)

        for i in range(1, MAX_VISUAL_PERSONS + 1):
            img = self._load_img(f'waiting_{i}.png', scale=WAITING_ICON_SCALE, optional=True)
            self.waiting_images.append(img)

        self.width = self.images['housing'].get_width()
        self.height = self.images['housing'].get_height()
        self.center_x = self.width // 2
        self.center_y = self.height // 2
        self.led_radius = int(ORIGINAL_LED_RADIUS * SCALE_FACTOR)
        self.dot_size_base = max(2, int(ORIGINAL_DOT_SIZE * SCALE_FACTOR))
        self.game_font = pygame.freetype.SysFont("Arial", int(TIMER_FONT_SIZE * SCALE_FACTOR), bold=True)

    def _load_img(self, filename, scale=SCALE_FACTOR, optional=False):
        path = os.path.join(ASSET_DIR, filename)
        if not os.path.exists(path):
            if optional:
                return None
            debug_log(f"Datei fehlt: {path}")
            sys.exit(1)
        img = pygame.image.load(path).convert_alpha()
        return pygame.transform.smoothscale(img, (int(img.get_width() * scale), int(img.get_height() * scale)))

    def draw_crowd_image(self, surface, person_count):
        if person_count <= 0:
            return
        idx = min(person_count, MAX_VISUAL_PERSONS) - 1
        if self.waiting_images and 0 <= idx < len(self.waiting_images) and self.waiting_images[idx]:
            rect = self.waiting_images[idx].get_rect(center=(self.center_x, self.center_y + OFFSET_RING_Y))
            surface.blit(self.waiting_images[idx], rect)
        else:
            text = str(person_count)
            self.game_font.render_to(surface, (self.center_x - 10, self.center_y + OFFSET_RING_Y - 10), text, (255, 255, 255))

    def draw_countdown_timer(self, surface, remaining_ms):
        seconds = math.ceil(remaining_ms / 1000)
        if seconds < 1:
            seconds = 1
        text = str(seconds)
        text_rect = self.game_font.get_rect(text)
        x = self.center_x - (text_rect.width // 2)
        y = self.center_y + OFFSET_RING_Y - (text_rect.height // 2)
        self.game_font.render_to(surface, (x, y), text, (255, 255, 255))

    def draw_led_ring(self, surface, active_leds, total_leds, state, breathing_alpha=255):
        ring_center_y = self.center_y + OFFSET_RING_Y
        current_dot_size = self.dot_size_base
        if total_leds > 60:
            current_dot_size = max(2, int(self.dot_size_base * (60 / total_leds)))

        # Glow-Größe für beleuchtete Punkte (sehr dezent)
        glow_radius = current_dot_size + 2

        for i in range(total_leds):
            angle = math.radians(-90 + (360 / total_leds) * i)
            x_int = int(self.center_x + self.led_radius * math.cos(angle))
            y_int = int(ring_center_y + self.led_radius * math.sin(angle))

            is_lit = False
            current_color = COLOR_LED_OFF

            if state == STATE_GREEN:
                leds_gone = total_leds - active_leds
                shifted_i = (i - 1) % total_leds
                if shifted_i >= leds_gone:
                    is_lit = True
                    current_color = COLOR_LED_ON
            elif state == STATE_RED:
                if i < active_leds:
                    is_lit = True
                    current_color = COLOR_LED_ON
            elif state == STATE_TRAM:
                leds_gone = total_leds - active_leds
                shifted_i = (i - 1) % total_leds
                if shifted_i >= leds_gone:
                    is_lit = True
                    current_color = COLOR_LED_ON
            elif state == STATE_CLEARANCE:
                is_lit = True
                current_color = COLOR_CLEARANCE
            elif state == STATE_SAFETY_1:
                is_lit = True
                current_color = COLOR_LED_ON

            if is_lit:
                # Alle beleuchteten Dots über SRCALPHA-Surface rendern (verhindert schwarze Vierecke)
                dot_alpha = breathing_alpha if state == STATE_CLEARANCE else 255
                r, g, b = current_color

                # Dezenter Glow-Effekt hinter dem Punkt
                glow_surf_size = (glow_radius * 2) + 4
                glow_center = glow_surf_size // 2
                glow_surf = pygame.Surface((glow_surf_size, glow_surf_size), pygame.SRCALPHA)
                glow_color = (r, g, b, max(10, dot_alpha // 8))
                pygame.draw.circle(glow_surf, glow_color, (glow_center, glow_center), glow_radius)
                surface.blit(glow_surf, (x_int - glow_center, y_int - glow_center))

                # Hauptpunkt
                dot_surf_size = (current_dot_size * 2) + 4
                dot_center = dot_surf_size // 2
                dot_surf = pygame.Surface((dot_surf_size, dot_surf_size), pygame.SRCALPHA)
                pygame.draw.circle(dot_surf, (r, g, b, dot_alpha), (dot_center, dot_center), current_dot_size)
                surface.blit(dot_surf, (x_int - dot_center, y_int - dot_center))
            else:
                # Inaktive Dots – dezent ohne Glow
                gfxdraw.filled_circle(surface, x_int, y_int, current_dot_size, COLOR_LED_OFF)
                gfxdraw.aacircle(surface, x_int, y_int, current_dot_size, COLOR_LED_OFF)

    def render(self, state, visual_active_leds, person_count, p_green, clearance_alpha, now,
               clearance_start_time, tram_active, green_leds_left_float):
        """Rendert die komplette Ampel-Ansicht auf ein eigenes Surface."""
        surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        surface.fill((0, 0, 0, 255))

        # Gehäuse
        housing_rect = self.images['housing'].get_rect(center=(self.center_x, self.center_y))
        surface.blit(self.images['housing'], housing_rect)

        pos_rot = (self.center_x, self.center_y + OFFSET_ROT_Y)
        pos_gruen = (self.center_x, self.center_y + OFFSET_GRUEN_Y)
        pos_tram = (self.center_x, self.center_y + OFFSET_TRAM_Y)

        # Ampelmännchen
        if p_green == 1:
            surface.blit(self.images['red_off'], self.images['red_off'].get_rect(center=pos_rot))
            surface.blit(self.images['green_on'], self.images['green_on'].get_rect(center=pos_gruen))
        else:
            surface.blit(self.images['red_on'], self.images['red_on'].get_rect(center=pos_rot))
            surface.blit(self.images['green_off'], self.images['green_off'].get_rect(center=pos_gruen))

        # Zustands-abhängiges Rendering
        if state == STATE_TRAM:
            tram_rect = self.images['tram'].get_rect(center=pos_tram)
            surface.blit(self.images['tram'], tram_rect)
            self.draw_led_ring(surface, visual_active_leds, VISUAL_LED_COUNT, STATE_TRAM, 255)

        elif state == STATE_CLEARANCE:
            self.draw_led_ring(surface, VISUAL_LED_COUNT, VISUAL_LED_COUNT, STATE_CLEARANCE, clearance_alpha)
            time_left = TIME_CLEARANCE - (now - clearance_start_time)
            self.draw_countdown_timer(surface, time_left)

        elif state == STATE_GREEN:
            if tram_active and self.images.get('tram'):
                breath_alpha = int(153 + 102 * math.sin(now * 0.003))
                tram_surf = self.images['tram'].copy()
                tram_surf.set_alpha(breath_alpha)
                tram_rect = tram_surf.get_rect(center=pos_tram)
                surface.blit(tram_surf, tram_rect)
            else:
                # Personen-Icons auch während Grünphase anzeigen
                self.draw_crowd_image(surface, person_count)
            self.draw_led_ring(surface, visual_active_leds, VISUAL_LED_COUNT, STATE_GREEN, 255)

        elif state == STATE_RED:
            self.draw_crowd_image(surface, person_count)
            self.draw_led_ring(surface, visual_active_leds, VISUAL_LED_COUNT, STATE_RED, 255)

        elif state == STATE_SAFETY_1:
            self.draw_crowd_image(surface, person_count)
            self.draw_led_ring(surface, VISUAL_LED_COUNT, VISUAL_LED_COUNT, STATE_RED, 255)

        elif state == STATE_IDLE:
            self.draw_crowd_image(surface, person_count)
            self.draw_led_ring(surface, 0, VISUAL_LED_COUNT, STATE_IDLE, 255)

        return surface


# ==========================================
#      HAUPT-ANWENDUNG
# ==========================================

def main():
    parser = argparse.ArgumentParser(description="Integrierte Ampel + Personenerkennung")
    parser.add_argument("--source", default="0", help="Kameraindex oder Stream-URL")
    parser.add_argument("--no-esp", action="store_true", help="ESP deaktivieren")
    parser.add_argument("--windowed", action="store_true", help="Feste Fenstergröße 1600x900 (Standard: 85%% Bildschirm)")
    args = parser.parse_args()

    # Source parsen
    source = args.source.strip()
    if source.isdigit():
        source = int(source)

    # === Pygame Init ===
    os.environ['SDL_VIDEO_CENTERED'] = '1'
    pygame.init()

    # Bildschirmauflösung erkennen
    display_info = pygame.display.Info()
    native_w = display_info.current_w
    native_h = display_info.current_h
    debug_log(f"Erkannte Bildschirmauflösung: {native_w}x{native_h}")

    if args.windowed:
        # Expliziter Fenstermodus mit fester Größe
        SCREEN_W = 1600
        SCREEN_H = 900
    else:
        # Standard: normales Fenster, 85% der Bildschirmfläche
        SCREEN_W = int(native_w * 0.85)
        SCREEN_H = int(native_h * 0.85)

    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.RESIZABLE)

    pygame.display.set_caption("TrafficOwl – Integriertes System")

    # === Ampel-Interface laden ===
    traffic_ui = TrafficInterface()
    traffic_ui.load_images()

    # === ESP Init ===
    esp = None
    if ESP_AVAILABLE and not args.no_esp:
        port = get_auto_port()
        esp = ESPController(port=port)
        esp.connect()
        if not esp.connected:
            debug_log(f"ESP konnte nicht verbunden werden auf {port}. Fahre ohne ESP fort.")
            esp = None
    last_esp_values = None

    # === Kamera-Detektor starten ===
    detector = CameraDetector(source=source)
    camera_ok = detector.start()
    if not camera_ok:
        debug_log("Kamera-Erkennung konnte nicht gestartet werden. Interface läuft ohne Kamera.")

    # === Zustandsvariablen ===
    clock = pygame.time.Clock()
    current_state = STATE_IDLE
    timer_total_duration_red = DURATION_RED_BASE_MS
    timer_elapsed = 0
    green_leds_left_float = 0.0
    clearance_start_time = 0
    tram_display_timer = 0
    person_count = 0
    camera_person_count = 0
    slow_mode_active = False
    visual_active_leds = 0
    tram_active = False

    # Trigger-Logik: Neuer Zyklus nur wenn Personen vorher auf 0 waren
    cycle_was_zero = True  # Startet als True, damit der erste Erkennungsfall triggert

    # ESP Hall-Sensor Debouncing
    esp_sensor_debounce_values = [0] * 8   # Geglättete Sensorwerte
    esp_sensor_pending = [0] * 8           # Anstehende Werte
    esp_sensor_pending_time = [0.0] * 8    # Zeitstempel der letzten Änderung
    ESP_SENSOR_DEBOUNCE_TIME = 0.3         # 300ms Debounce für Sensoren

    # Placeholder-Surface wenn keine Kamera
    no_cam_font = pygame.font.SysFont("Arial", 30)

    running = True
    while running:
        dt = clock.tick(60)
        now = pygame.time.get_ticks()

        # === Events ===
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.VIDEORESIZE:
                SCREEN_W, SCREEN_H = event.w, event.h
                screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.RESIZABLE)
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                if event.key == pygame.K_f:
                    # Fullscreen-Toggle mit F-Taste
                    if screen.get_flags() & pygame.FULLSCREEN:
                        SCREEN_W = int(native_w * 0.85)
                        SCREEN_H = int(native_h * 0.85)
                        screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.RESIZABLE)
                    else:
                        SCREEN_W = native_w
                        SCREEN_H = native_h
                        screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.FULLSCREEN)

                if event.key == pygame.K_g and current_state == STATE_IDLE:
                    debug_log("G-Taste: Starte Rotphase.")
                    current_state = STATE_RED
                    timer_elapsed = 0
                    timer_total_duration_red = DURATION_RED_BASE_MS + TIME_SAFETY_PRE_GREEN
                    if esp:
                        esp.set_pulsing(True)

                if event.key == pygame.K_t:
                    debug_log("T-Taste: Tram!")
                    if current_state == STATE_CLEARANCE:
                        debug_log("Tram ignoriert: Räumzeit läuft.")
                    elif current_state == STATE_GREEN:
                        tram_active = True
                        green_leds_left_float = float(VISUAL_LED_COUNT)
                        slow_mode_active = False
                    else:
                        current_state = STATE_TRAM
                        timer_elapsed = 0
                        tram_active = True
                        tram_display_timer = now

                if event.key == pygame.K_SPACE:
                    if current_state == STATE_GREEN:
                        slow_mode_active = not slow_mode_active
                        debug_log(f"Slow Mode: {slow_mode_active}")

                if event.key == pygame.K_UP:
                    person_count = min(MAX_PERSON_CAP, person_count + 1)
                if event.key == pygame.K_DOWN:
                    person_count = max(0, person_count - 1)

        # === Kamera-Daten abrufen ===
        cam_frame, cam_count = detector.get_frame_and_count()
        camera_person_count = cam_count

        # Personen-Zusammenführung: Maximum aus Kamera und ESP-Sensoren
        # (ESP-Sensoren werden unten gelesen und ebenfalls in person_count gespeichert)
        # Kamera-Count hat Vorrang / wird addiert mit HAL-Sensor-Count
        esp_sensor_person_count = 0

        # === ESP Daten lesen ===
        if esp and esp.connected:
            # Button 1 (Start)
            if esp.button_pressed:
                esp.button_pressed = False
                if current_state == STATE_IDLE:
                    debug_log("ESP Button 1: Starte Rotphase.")
                    current_state = STATE_RED
                    timer_elapsed = 0
                    timer_total_duration_red = DURATION_RED_BASE_MS + TIME_SAFETY_PRE_GREEN
                    esp.set_pulsing(True)

            # Button 2 (Slow)
            if esp.button2_pressed:
                esp.button2_pressed = False
                if current_state == STATE_GREEN:
                    slow_mode_active = not slow_mode_active
                    debug_log(f"ESP Button 2: Slow Mode = {slow_mode_active}")

            # Sensor-Daten lesen (MUSS vor Tram-Check und Debounce stehen!)
            sensor_count = esp.read_sensor_data()

            # Hall-Sensor Debouncing (Personen-Sensoren Index 0-5)
            current_time_s = time.time()
            for si in range(min(6, len(esp.sensor_values))):
                raw_val = esp.sensor_values[si]
                if raw_val != esp_sensor_pending[si]:
                    esp_sensor_pending[si] = raw_val
                    esp_sensor_pending_time[si] = current_time_s
                else:
                    if current_time_s - esp_sensor_pending_time[si] >= ESP_SENSOR_DEBOUNCE_TIME:
                        esp_sensor_debounce_values[si] = esp_sensor_pending[si]

            # Tram-Sensoren: Latched-Flag aus ESPController nutzen
            # (read_sensor_data() merkt sich jede 1 auf Sensor 6/7, auch kurze Flanken)
            if esp.tram_triggered:
                esp.tram_triggered = False  # Flag zurücksetzen (einmalig konsumieren)
                if not tram_active and current_state != STATE_CLEARANCE:
                    debug_log(f"Tram erkannt (Sensor)! debounce[6]={esp_sensor_debounce_values[6]}, debounce[7]={esp_sensor_debounce_values[7]}")
                    if current_state == STATE_GREEN:
                        tram_active = True
                        green_leds_left_float = float(VISUAL_LED_COUNT)
                        slow_mode_active = False
                    elif current_state != STATE_TRAM:
                        current_state = STATE_TRAM
                        timer_elapsed = 0
                        tram_active = True
                        tram_display_timer = now

            esp_sensor_person_count = min(MAX_PERSON_CAP, sum(esp_sensor_debounce_values[:6]))

        # Personen zusammenführen: Kamera + HAL-Sensoren (Maximum)
        combined_count = max(camera_person_count, esp_sensor_person_count)
        person_count = min(MAX_PERSON_CAP, combined_count)

        # Trigger-Logik: Neuer Zyklus nur wenn vorher 0 Personen waren
        if person_count == 0:
            cycle_was_zero = True

        # === ZEIT-FAKTOR ===
        current_time_factor = 1.0
        if current_state == STATE_RED:
            current_time_factor = 1.0 + ((person_count / 5) * CROWD_BONUS_FACTOR)

        # FADING Clearance
        clearance_alpha = 255
        if current_state == STATE_CLEARANCE:
            clearance_alpha = int(128 + 127 * math.sin(now * 0.020))

        # === ZUSTANDS-LOGIK ===

        if current_state == STATE_IDLE:
            if person_count > 0 and cycle_was_zero:
                debug_log(f"Person(en) erkannt ({person_count})! Starte Rotphase.")
                cycle_was_zero = False
                current_state = STATE_RED
                timer_elapsed = 0
                timer_total_duration_red = DURATION_RED_BASE_MS + TIME_SAFETY_PRE_GREEN
                if esp:
                    esp.set_pulsing(True)

        elif current_state == STATE_TRAM:
            timer_elapsed += dt
            ratio = timer_elapsed / TIME_TRAM_PRE_GREEN
            leds_visible_ratio = max(0.0, 1.0 - ratio)
            visual_active_leds = int(leds_visible_ratio * VISUAL_LED_COUNT)

            if timer_elapsed >= TIME_TRAM_PRE_GREEN:
                current_state = STATE_GREEN
                timer_elapsed = 0
                green_leds_left_float = float(VISUAL_LED_COUNT)
                slow_mode_active = False

        elif current_state == STATE_RED:
            timer_elapsed += dt * current_time_factor
            ratio = min(1.0, timer_elapsed / timer_total_duration_red)
            visual_active_leds = int(ratio * VISUAL_LED_COUNT)

            if timer_elapsed >= timer_total_duration_red:
                current_state = STATE_GREEN
                timer_elapsed = 0
                if esp:
                    esp.set_pulsing(False)
                bonus_leds = person_count * ADD_LEDS_PER_PERSON
                green_leds_left_float = float(BASE_LEDS_GREEN + bonus_leds)
                if green_leds_left_float > MAX_LEDS_LIMIT:
                    green_leds_left_float = float(MAX_LEDS_LIMIT)
                slow_mode_active = False

        elif current_state == STATE_SAFETY_1:
            timer_elapsed += dt
            visual_active_leds = VISUAL_LED_COUNT
            if timer_elapsed >= TIME_SAFETY_PRE_GREEN:
                current_state = STATE_GREEN
                timer_elapsed = 0
                if esp:
                    esp.set_pulsing(False)

        elif current_state == STATE_GREEN:
            if tram_active:
                seconds_per_led = TIME_TRAM_GREEN_DURATION / 1000.0 / VISUAL_LED_COUNT
            else:
                seconds_per_led = SECONDS_PER_LED_GREEN_SLOW if slow_mode_active else SECONDS_PER_LED_GREEN
            ms_per_led = seconds_per_led * 1000
            points_consumed = dt / ms_per_led
            green_leds_left_float -= points_consumed
            visual_active_leds = min(VISUAL_LED_COUNT, int(green_leds_left_float))

            if green_leds_left_float <= 0:
                current_state = STATE_CLEARANCE
                clearance_start_time = now
                visual_active_leds = VISUAL_LED_COUNT

        elif current_state == STATE_CLEARANCE:
            if now - clearance_start_time > TIME_CLEARANCE:
                current_state = STATE_IDLE
                timer_elapsed = 0
                person_count = 0
                slow_mode_active = False
                tram_active = False
                if esp:
                    esp.set_pulsing(False)
                debug_log("Zyklus beendet.")

        # === HARDWARE AMPEL LOGIK ===
        p_red, p_green = 1, 0
        c_red, c_yellow, c_green = 0, 0, 1

        if current_state == STATE_IDLE:
            pass
        elif current_state == STATE_RED:
            time_left = timer_total_duration_red - timer_elapsed
            if time_left <= TIME_SAFETY_PRE_GREEN:
                c_red, c_yellow, c_green = 1, 0, 0
            elif time_left <= (TIME_SAFETY_PRE_GREEN + TIME_CAR_YELLOW):
                c_red, c_yellow, c_green = 0, 1, 0
            else:
                c_red, c_yellow, c_green = 0, 0, 1
        elif current_state == STATE_SAFETY_1:
            c_red, c_yellow, c_green = 1, 0, 0
        elif current_state == STATE_GREEN:
            p_red, p_green = 0, 1
            c_red, c_yellow, c_green = 1, 0, 0
        elif current_state == STATE_CLEARANCE:
            p_red, p_green = 1, 0
            time_passed = now - clearance_start_time
            time_left_clearance = TIME_CLEARANCE - time_passed
            if time_left_clearance < TIME_CAR_RED_YELLOW:
                c_red, c_yellow, c_green = 1, 1, 0
            else:
                c_red, c_yellow, c_green = 1, 0, 0
        elif current_state == STATE_TRAM:
            if timer_elapsed < TIME_TRAM_YELLOW:
                c_red, c_yellow, c_green = 0, 1, 0
            else:
                c_red, c_yellow, c_green = 1, 0, 0
            p_red, p_green = 1, 0

        # ESP LEDs senden
        if esp and esp.connected:
            current_values = (p_red, p_green, c_red, c_yellow, c_green)
            if current_values != last_esp_values or (now % 2000 < dt):
                esp.update_leds(*current_values)
                last_esp_values = current_values

        # === RENDERING ===
        screen.fill((12, 12, 14))

        # --- Layout berechnen ---
        status_bar_h = 36
        content_h = SCREEN_H - status_bar_h
        interface_area_w = max(160, SCREEN_W // 6)
        cam_area_w = SCREEN_W - interface_area_w
        margin = 6

        # --- RECHTS: Panel-Hintergrund ---
        panel_x = SCREEN_W - interface_area_w
        panel_w = interface_area_w
        pygame.draw.rect(screen, (14, 14, 16), (panel_x, 0, panel_w, content_h))
        # Trennlinie
        pygame.draw.line(screen, (32, 32, 36), (panel_x, 0), (panel_x, content_h), 1)

        # --- LINKS: Kamerabild (korrekt skaliert, kein Abschneiden) ---
        if cam_frame is not None:
            cam_h_src, cam_w_src = cam_frame.shape[:2]
            # Skalieren damit das Bild in den verfügbaren Bereich passt (aspect ratio beibehalten)
            scale_w = cam_area_w / cam_w_src
            scale_h = content_h / cam_h_src
            cam_scale = min(scale_w, scale_h)  # fit (kein Abschneiden)
            new_cam_w = int(cam_w_src * cam_scale)
            new_cam_h = int(cam_h_src * cam_scale)
            resized = cv2.resize(cam_frame, (new_cam_w, new_cam_h))
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            cam_surface = pygame.surfarray.make_surface(rgb.swapaxes(0, 1))

            # Zentriert im Kamerabereich platzieren
            cam_x = (cam_area_w - new_cam_w) // 2
            cam_y = (content_h - new_cam_h) // 2
            screen.blit(cam_surface, (cam_x, cam_y))
        else:
            # Placeholder
            placeholder = pygame.Surface((cam_area_w, content_h))
            placeholder.fill((16, 16, 18))
            text_surf = no_cam_font.render("Kamera wird initialisiert...", True, (60, 60, 60))
            text_rect = text_surf.get_rect(center=(cam_area_w // 2, content_h // 2))
            placeholder.blit(text_surf, text_rect)
            screen.blit(placeholder, (0, 0))

        # --- Ampel-Visualisierung rendern ---
        ampel_surface = traffic_ui.render(
            state=current_state,
            visual_active_leds=visual_active_leds,
            person_count=person_count,
            p_green=p_green,
            clearance_alpha=clearance_alpha,
            now=now,
            clearance_start_time=clearance_start_time,
            tram_active=tram_active,
            green_leds_left_float=green_leds_left_float
        )

        # Ampel skalieren für das rechte Panel
        ampel_h = ampel_surface.get_height()
        ampel_w = ampel_surface.get_width()
        panel_inner_w = panel_w - margin * 2
        panel_inner_h = content_h - margin * 2
        scale_factor = min(panel_inner_w / ampel_w, panel_inner_h / ampel_h)
        scaled_ampel_w = int(ampel_w * scale_factor)
        scaled_ampel_h = int(ampel_h * scale_factor)
        scaled_ampel = pygame.transform.smoothscale(ampel_surface, (scaled_ampel_w, scaled_ampel_h))

        # Zentriert im Panel
        ampel_x = panel_x + (panel_w - scaled_ampel_w) // 2
        ampel_y = (content_h - scaled_ampel_h) // 2
        screen.blit(scaled_ampel, (ampel_x, ampel_y))

        # ─── MODERNE STATUS-LEISTE UNTEN ───
        bar_y = SCREEN_H - status_bar_h
        # Hintergrund
        bar_surf = pygame.Surface((SCREEN_W, status_bar_h), pygame.SRCALPHA)
        bar_surf.fill((18, 18, 22, 240))
        screen.blit(bar_surf, (0, bar_y))
        # Obere Linie
        pygame.draw.line(screen, (40, 40, 48), (0, bar_y), (SCREEN_W, bar_y), 1)

        # Status-Farbe
        state_color = (80, 220, 80) if current_state == STATE_GREEN else \
                      (220, 70, 70) if current_state == STATE_RED else \
                      (220, 180, 40) if current_state == STATE_CLEARANCE else \
                      (60, 180, 220) if current_state == STATE_TRAM else (100, 100, 100)

        # Status-Punkt (farbiger Indikator)
        dot_x = 16
        dot_y = bar_y + status_bar_h // 2
        pygame.draw.circle(screen, state_color, (dot_x, dot_y), 5)
        # Mini-Glow
        dot_glow = pygame.Surface((18, 18), pygame.SRCALPHA)
        pygame.draw.circle(dot_glow, (*state_color, 30), (9, 9), 9)
        screen.blit(dot_glow, (dot_x - 9, dot_y - 9))

        # Text-Rendering (modern, sauber)
        sf = pygame.font.SysFont("Helvetica", 13)
        sf_bold = pygame.font.SysFont("Helvetica", 13, bold=True)

        # Status-Label
        state_label = sf_bold.render(current_state, True, state_color)
        screen.blit(state_label, (dot_x + 12, bar_y + 10))

        # Trenner und Info-Segmente
        info_x = dot_x + 12 + state_label.get_width() + 20
        separator_color = (50, 50, 55)

        segments = []
        segments.append(("Kamera", str(camera_person_count), (160, 160, 170)))
        segments.append(("ESP", str(esp_sensor_person_count), (160, 160, 170)))
        segments.append(("Gesamt", str(person_count), (220, 220, 230)))

        if esp and esp.connected:
            segments.append(("ESP", "●", (60, 200, 80)))
        else:
            segments.append(("ESP", "○", (100, 100, 100)))

        if slow_mode_active:
            segments.append(("", "SLOW", (220, 170, 40)))

        if tram_active:
            segments.append(("", "TRAM", (60, 180, 220)))

        for label_text, value_text, val_color in segments:
            # Trennstrich
            pygame.draw.line(screen, separator_color, (info_x, bar_y + 8), (info_x, bar_y + status_bar_h - 8), 1)
            info_x += 12

            if label_text:
                lbl = sf.render(f"{label_text} ", True, (90, 90, 100))
                screen.blit(lbl, (info_x, bar_y + 10))
                info_x += lbl.get_width()

            val = sf_bold.render(value_text, True, val_color)
            screen.blit(val, (info_x, bar_y + 10))
            info_x += val.get_width() + 16

        # Rechte Seite: Tastenkürzel
        keys_text = "[F] Vollbild   [G] Start   [T] Tram   [SPACE] Slow   [ESC] Beenden"
        keys_surf = sf.render(keys_text, True, (60, 60, 68))
        screen.blit(keys_surf, (SCREEN_W - keys_surf.get_width() - 12, bar_y + 10))

        pygame.display.flip()

    # === Cleanup ===
    debug_log("Beende Anwendung...")
    detector.stop()
    if esp:
        esp.close()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
