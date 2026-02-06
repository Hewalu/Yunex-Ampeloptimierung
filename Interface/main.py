import pygame
import pygame.freetype
from pygame import gfxdraw
import math
import sys
import os
import serial.tools.list_ports

# Hardware-Module laden
try:
    from esp_control import ESPController
    ESP_AVAILABLE = True
except ImportError:
    ESP_AVAILABLE = False
    print("[SYSTEM] 'esp_control.py' nicht gefunden. Starte im Simulations-Modus.")

try:
    from traffic_logic import TrafficLightLogic
    LOGIC_AVAILABLE = True
except ImportError:
    LOGIC_AVAILABLE = False

# ==========================================
#      KONFIGURATION DER ZEITEN
# ==========================================


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
    return "COM3"


ESP_PORT = get_auto_port()
SCALE_FACTOR = 0.3

# 1. PERSONEN LOGIK
MAX_PERSON_CAP = 8
MAX_VISUAL_PERSONS = 8
ADD_LEDS_PER_PERSON = 1
CROWD_BONUS_FACTOR = 0.3

# 2. LED SETUP
# Wir nutzen 25 Punkte für Grün (voller Ring).
BASE_LEDS_GREEN = 25
VISUAL_LED_COUNT = 25
TOTAL_LEDS_RED = 25
MAX_LEDS_LIMIT = 30

# 3. GESCHWINDIGKEITEN
SECONDS_PER_LED_RED = 0.20   # Wartezeit füllen
SECONDS_PER_LED_GREEN = 0.333  # Normales Ablaufen
SECONDS_PER_LED_GREEN_SLOW = 0.5    # Langsames Ablaufen (Taste)

# 4. FESTE PHASEN (in Millisekunden)
TIME_SAFETY_PRE_GREEN = 3000  # Puffer bevor Fußgänger Grün bekommen (Alle Rot)
TIME_CLEARANCE = 11000  # Räumzeit am Ende
TIME_CAR_YELLOW = 3000  # Wie lange Autos Gelb haben vor Rot
TIME_CAR_RED_YELLOW = 1500  # Wie lange Autos Rot-Gelb haben vor Grün

# Tram Zeiten
TIME_TRAM_PRE_GREEN = 5000     # 5s "Safety" (3s Gelb + 2s Buffer)
TIME_TRAM_GREEN_DURATION = 25000  # 25s Grünphase bei Tram
TIME_TRAM_YELLOW = 3000
TIME_TRAM_SAFETY = 2000

# Basis-Dauer Rotphase berechnen
DURATION_RED_BASE_MS = int(TOTAL_LEDS_RED * SECONDS_PER_LED_RED * 1000)

# 5. OPTIK / FARBEN
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

# ==========================================
# SYSTEM CODE
# ==========================================

WIDTH, HEIGHT = 0, 0
CENTER_X, CENTER_Y = 0, 0
LED_RADIUS = 0
DOT_SIZE_BASE = 0
images = {}
waiting_images = []
game_font = None

# ZUSTÄNDE
STATE_IDLE = "IDLE"           # Alles ruhig, Auto Grün
STATE_RED = "RED"             # Wartezeit füllt sich
STATE_SAFETY_1 = "SAFETY_1"   # Puffer, Alle Rot
STATE_GREEN = "GREEN"         # Gehen
STATE_CLEARANCE = "CLEARANCE"  # Räumen
STATE_TRAM = "TRAM"


def debug_log(message):
    print(f"[DEBUG] {message}", flush=True)


def load_and_scale_image(path, scale=SCALE_FACTOR):
    try:
        if not os.path.exists(path):
            if "tram" in path or "waiting" in path:
                return None
            else:
                raise FileNotFoundError(f"Datei fehlt: {path}")
        img = pygame.image.load(path).convert_alpha()
        return pygame.transform.smoothscale(img, (int(img.get_width()*scale), int(img.get_height()*scale)))
    except Exception as e:
        debug_log(f"Fehler bei {path}: {e}")
        sys.exit()


def load_images():
    global game_font, waiting_images
    script_dir = os.path.dirname(os.path.abspath(__file__))
    asset_dir = os.path.join(script_dir, "assets")
    if not os.path.exists(asset_dir):
        sys.exit()

    images['housing'] = load_and_scale_image(os.path.join(asset_dir, 'gehaeuse.png'))
    images['red_on'] = load_and_scale_image(os.path.join(asset_dir, 'mann_rot_an.png'))
    images['red_off'] = load_and_scale_image(os.path.join(asset_dir, 'mann_rot_aus.png'))
    images['green_on'] = load_and_scale_image(os.path.join(asset_dir, 'mann_gruen_an.png'))
    images['green_off'] = load_and_scale_image(os.path.join(asset_dir, 'mann_gruen_aus.png'))
    # Tram etwas kleiner skalieren (Faktor 0.7 vom Standard)
    images['tram'] = load_and_scale_image(os.path.join(asset_dir, 'tram.png'), scale=SCALE_FACTOR * 0.7)

    for i in range(1, MAX_VISUAL_PERSONS + 1):
        filename = f"waiting_{i}.png"
        full_path = os.path.join(asset_dir, filename)
        img = load_and_scale_image(full_path, scale=WAITING_ICON_SCALE)
        if img:
            waiting_images.append(img)
        else:
            waiting_images.append(None)

    global WIDTH, HEIGHT, CENTER_X, CENTER_Y, LED_RADIUS, DOT_SIZE_BASE
    WIDTH = images['housing'].get_width()
    HEIGHT = images['housing'].get_height()
    CENTER_X, CENTER_Y = WIDTH // 2, HEIGHT // 2
    LED_RADIUS = int(ORIGINAL_LED_RADIUS * SCALE_FACTOR)
    DOT_SIZE_BASE = max(2, int(ORIGINAL_DOT_SIZE * SCALE_FACTOR))
    game_font = pygame.freetype.SysFont("Arial", int(TIMER_FONT_SIZE * SCALE_FACTOR), bold=True)

# --- ZEICHNEN ---


def draw_crowd_image(screen, person_count):
    if person_count <= 0:
        return
    idx = min(person_count, MAX_VISUAL_PERSONS) - 1
    if waiting_images and 0 <= idx < len(waiting_images) and waiting_images[idx]:
        rect = waiting_images[idx].get_rect(center=(CENTER_X, CENTER_Y + OFFSET_RING_Y))
        screen.blit(waiting_images[idx], rect)
    else:
        text = str(person_count)
        game_font.render_to(screen, (CENTER_X-10, CENTER_Y+OFFSET_RING_Y-10), text, (255, 255, 255))


def draw_countdown_timer(screen, remaining_ms):
    seconds = math.ceil(remaining_ms / 1000)
    if seconds < 1:
        seconds = 1
    text = str(seconds)
    text_rect = game_font.get_rect(text)
    x = CENTER_X - (text_rect.width // 2)
    y = CENTER_Y + OFFSET_RING_Y - (text_rect.height // 2)
    game_font.render_to(screen, (x, y), text, (255, 255, 255))


def draw_led_ring(screen, active_leds, total_leds, state, breathing_alpha=255):
    ring_center_y = CENTER_Y + OFFSET_RING_Y
    current_dot_size = DOT_SIZE_BASE
    if total_leds > 60:
        current_dot_size = max(2, int(DOT_SIZE_BASE * (60/total_leds)))
    surf_size = (current_dot_size * 2) + 4
    center_offset = surf_size // 2

    for i in range(total_leds):
        # -90 Grad ist 12 Uhr
        angle = math.radians(-90 + (360 / total_leds) * i)
        x_int = int(CENTER_X + LED_RADIUS * math.cos(angle))
        y_int = int(ring_center_y + LED_RADIUS * math.sin(angle))

        is_lit = False
        current_color = COLOR_LED_OFF

        # --- LOGIK ---
        if state == STATE_GREEN:
            # Weiß leert sich im Uhrzeigersinn (Index 0 zuletzt)
            leds_gone = total_leds - active_leds
            shifted_i = (i - 1) % total_leds
            if shifted_i >= leds_gone:
                is_lit = True
                current_color = COLOR_LED_ON

        elif state == STATE_RED:
            # Weiß füllt sich auf
            if i < active_leds:
                is_lit = True
                current_color = COLOR_LED_ON

        elif state == STATE_TRAM:
            # Weiß leert sich im Uhrzeigersinn (Countdown)
            leds_gone = total_leds - active_leds
            shifted_i = (i - 1) % total_leds
            if shifted_i >= leds_gone:
                is_lit = True
                current_color = COLOR_LED_ON

        elif state == STATE_CLEARANCE:
            is_lit = True
            current_color = COLOR_CLEARANCE  # Rot blinkend

        elif state == STATE_SAFETY_1:
            # Während Sicherheitszeit Ring voll lassen
            is_lit = True
            current_color = COLOR_LED_ON

        # --- ZEICHNEN ---
        if is_lit:
            if state == STATE_CLEARANCE:
                dot_surf = pygame.Surface((surf_size, surf_size), pygame.SRCALPHA)
                pygame.draw.circle(dot_surf, current_color, (center_offset, center_offset), current_dot_size)
                dot_surf.set_alpha(breathing_alpha)
                screen.blit(dot_surf, (x_int - center_offset, y_int - center_offset))
            else:
                gfxdraw.filled_circle(screen, x_int, y_int, current_dot_size, current_color)
                gfxdraw.aacircle(screen, x_int, y_int, current_dot_size, current_color)
        else:
            gfxdraw.filled_circle(screen, x_int, y_int, current_dot_size, COLOR_LED_OFF)
            gfxdraw.aacircle(screen, x_int, y_int, current_dot_size, COLOR_LED_OFF)


def main():
    os.environ['SDL_VIDEO_CENTERED'] = '1'
    debug_log("Starte Programm...")
    pygame.init()
    pygame.display.set_mode((100, 100))
    load_images()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Traffic Light Control")

    # --- HARDWARE INIT ---
    esp = None
    if ESP_AVAILABLE:
        esp = ESPController(port=ESP_PORT)
        esp.connect()
    last_esp_values = None

    clock = pygame.time.Clock()

    current_state = STATE_IDLE

    # Timer Variablen
    timer_total_duration_red = DURATION_RED_BASE_MS
    timer_elapsed = 0

    # Float-Tank für Grünphase
    green_leds_left_float = 0.0

    clearance_start_time = 0
    tram_display_timer = 0
    person_count = 0

    slow_mode_active = False

    visual_active_leds = 0
    
    # Flags für Tram-Modus
    tram_active = False  # Wenn True, sind wir in einem Tram-Zyklus (längeres Grün + Icon)
    
    running = True
    while running:
        dt = clock.tick(60)
        now = pygame.time.get_ticks()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_g and current_state == STATE_IDLE:
                    debug_log("Knopf gedrückt! Starte Rotphase.")
                    current_state = STATE_RED
                    timer_elapsed = 0
                    timer_total_duration_red = DURATION_RED_BASE_MS + TIME_SAFETY_PRE_GREEN
                    if esp:
                        esp.set_pulsing(True)

                if event.key == pygame.K_t:
                    debug_log("T-Taste gedrückt (Tram)!")
                    if current_state == STATE_CLEARANCE:
                         debug_log("Tram ignoriert: Räumzeit läuft.")
                    elif current_state == STATE_GREEN:
                        # Wenn bereits GRÜN, dann Tram-Modus aktivieren und Zeit resetten (Verlängerung)
                        tram_active = True
                        debug_log("Tram während Grün! Verlängere Grünphase.")
                        # Reset float tank to full for 25s
                        green_leds_left_float = float(VISUAL_LED_COUNT)
                        slow_mode_active = False # Tram override slow mode defaults
                    else:
                        # Sonst Standard Tram Ablauf starten
                        current_state = STATE_TRAM
                        timer_elapsed = 0
                        tram_active = True # Zyklus beginnt
                        tram_display_timer = now # Für andere Animationszwecke

                if event.key == pygame.K_SPACE:
                    if current_state == STATE_GREEN:
                        slow_mode_active = not slow_mode_active
                        debug_log(f"Slow Mode: {slow_mode_active}")

                if event.key == pygame.K_UP:
                    person_count = min(MAX_PERSON_CAP, person_count + 1)
                if event.key == pygame.K_DOWN:
                    person_count = max(0, person_count - 1)

        # ZEIT-FAKTOR (Rot läuft schneller mit Leuten)
        current_time_factor = 1.0
        if current_state == STATE_RED:
            current_time_factor = 1.0 + ((person_count / 5) * CROWD_BONUS_FACTOR)

        # FADING für Clearance
        clearance_alpha = 255
        if current_state == STATE_CLEARANCE:
            clearance_alpha = int(128 + 127 * math.sin(now * 0.020))

        # ==========================================
        # ZUSTANDS LOGIK & TIMER
        # ==========================================

        # Check external Button (ESP)
        if esp:
            if esp.button_pressed:
                esp.button_pressed = False
                if current_state == STATE_IDLE:
                    debug_log("ESP Button 1! Starte Rotphase.")
                    current_state = STATE_RED
                    timer_elapsed = 0
                    timer_total_duration_red = DURATION_RED_BASE_MS + TIME_SAFETY_PRE_GREEN
                    esp.set_pulsing(True)

            if esp.button2_pressed:
                esp.button2_pressed = False
                # Toggle Slow Mode
                if current_state == STATE_GREEN:  # Nur während GRÜN relevant? Oder allgemein togglen?
                    # Anforderung: slow mode aktivieren. Interpretieren wir als Toggle.
                    # User Request sagt: "Der andere Button ist um den slow mode zu aktivieren"
                    # Ich mache es wie bei LEERTASTE:
                    slow_mode_active = not slow_mode_active
                    debug_log(f"ESP Button 2! Slow Mode: {slow_mode_active}")

            # Tram Sensoren Check (Indizes 6 und 7)
            # Wenn Tram erkannt, sofort in Tram-Modus wechseln (Override)
            if len(esp.sensor_values) >= 8:
                if esp.sensor_values[6] == 1 or esp.sensor_values[7] == 1:
                    # Nur Trigger wenn nicht schon im TRAM-Ablauf
                    if not tram_active and current_state != STATE_CLEARANCE:
                        debug_log("Tram erkannt (Sensor)!")
                        
                        if current_state == STATE_GREEN:
                             # Wenn bereits GRÜN, dann Tram-Modus aktivieren und Zeit resetten (Verlängerung)
                             tram_active = True
                             debug_log("Tram während Grün (Sensor)! Verlängere Grünphase.")
                             # Reset float tank to full for 25s
                             green_leds_left_float = float(VISUAL_LED_COUNT)
                             slow_mode_active = False
                        elif current_state != STATE_TRAM:
                             # Normaler Start Tram Zyklus
                            current_state = STATE_TRAM
                            timer_elapsed = 0
                            tram_active = True
                            tram_display_timer = now

        if current_state == STATE_IDLE:
            # Automatische Auslösung, wenn Personen erkannt werden
            if person_count > 0:
                debug_log("Person erkannt (Sensor)! Starte Rotphase.")
                current_state = STATE_RED
                timer_elapsed = 0
                timer_total_duration_red = DURATION_RED_BASE_MS + TIME_SAFETY_PRE_GREEN
                if esp:
                    esp.set_pulsing(True)

        elif current_state == STATE_TRAM:
            # Tram "Pre-Green" Phase: 5 Sekunden insgesamt
            timer_elapsed += dt
            
            # Visualisierung: Ring leert sich schnell (Countdown bis Grün)
            ratio = timer_elapsed / TIME_TRAM_PRE_GREEN  # 0->1
            # Inverse für Countdown
            leds_visible_ratio = 1.0 - ratio
            if leds_visible_ratio < 0: leds_visible_ratio = 0
            
            visual_active_leds = int(leds_visible_ratio * VISUAL_LED_COUNT)

            if timer_elapsed >= TIME_TRAM_PRE_GREEN:
                # Wechsel zu Grün (Tram Modus bleibt aktiv)
                current_state = STATE_GREEN
                timer_elapsed = 0
                
                # GRÜN TANK definieren (Fest 25s)
                # Wir manipulieren green_leds_left_float so, dass es für 25s reicht
                # Points needed = DurationMS / MS_per_LED
                # ABER mein Code unten nutzt SECONDS_PER_LED vars.
                # Wir setzen hier einfach einen Dummy-Wert und flaggen, dass wir feste Zeit nutzen.
                
                # Wir nutzen die existierende Logik: Tank voll machen (visual), aber Geschwindigkeit anpassen
                green_leds_left_float = float(VISUAL_LED_COUNT) 
                
                slow_mode_active = False

        # --- ROT PHASE (WARTEN) ---
        elif current_state == STATE_RED:
            timer_elapsed += dt * current_time_factor

            # Visualisierung
            ratio = timer_elapsed / timer_total_duration_red
            if ratio > 1:
                ratio = 1
            visual_active_leds = int(ratio * VISUAL_LED_COUNT)

            if timer_elapsed >= timer_total_duration_red:
                # Wechsel direkt zu GRÜN (Safety ist jetzt logisch Teil der Rot-Dauer)
                current_state = STATE_GREEN
                timer_elapsed = 0
                
                # VISUAL: Pulsieren aus, da jetzt Grün
                if esp:
                    esp.set_pulsing(False)

                # GRÜN TANK Vorbereiten
                bonus_leds = person_count * ADD_LEDS_PER_PERSON
                green_leds_left_float = float(BASE_LEDS_GREEN + bonus_leds)
                if green_leds_left_float > MAX_LEDS_LIMIT:
                    green_leds_left_float = float(MAX_LEDS_LIMIT)
                slow_mode_active = False

        # --- SAFETY 1 (ALLE ROT) ---
        elif current_state == STATE_SAFETY_1:
            timer_elapsed += dt
            # Ring bleibt voll
            visual_active_leds = VISUAL_LED_COUNT

            if timer_elapsed >= TIME_SAFETY_PRE_GREEN:
                # Wechsel zu GRÜN
                current_state = STATE_GREEN
                timer_elapsed = 0
                if esp:
                    esp.set_pulsing(False)

        # --- GRÜN PHASE (GEHEN) ---
        elif current_state == STATE_GREEN:
            # Wähle Geschwindigkeit
            if tram_active:
                # 25 Sekunden für den ganzen Ring
                # Total Points = VISUAL_LED_COUNT
                # Time = 25s
                # Seconds per LED = 25 / VISUAL_LED_COUNT = 1.0
                seconds_per_led = TIME_TRAM_GREEN_DURATION / 1000.0 / VISUAL_LED_COUNT
            else:
                seconds_per_led = SECONDS_PER_LED_GREEN_SLOW if slow_mode_active else SECONDS_PER_LED_GREEN
            
            ms_per_led = seconds_per_led * 1000

            # Tank leeren
            points_consumed = dt / ms_per_led
            green_leds_left_float -= points_consumed

            # Visualisierung
            visual_active_leds = int(green_leds_left_float)
            if visual_active_leds > VISUAL_LED_COUNT:
                visual_active_leds = VISUAL_LED_COUNT

            if green_leds_left_float <= 0:
                current_state = STATE_CLEARANCE
                clearance_start_time = now
                visual_active_leds = VISUAL_LED_COUNT  # Für Blinken voll machen

        # --- CLEARANCE (RÄUMEN) ---
        elif current_state == STATE_CLEARANCE:
            # Timer läuft via clearance_start_time
            if now - clearance_start_time > TIME_CLEARANCE:
                current_state = STATE_IDLE
                timer_elapsed = 0
                person_count = 0
                slow_mode_active = False
                tram_active = False  # Tram Zyklus beenden
                if esp:
                    esp.set_pulsing(False)
                debug_log("Zyklus beendet.")

        # ==========================================
        # HARDWARE / AMPEL LOGIK
        # ==========================================

        p_red, p_green = 1, 0
        c_red, c_yellow, c_green = 0, 0, 1  # Default Auto Grün

        if current_state == STATE_IDLE:
            # Standard: Auto fährt, Mensch wartet
            pass

        elif current_state == STATE_RED:
            # Auto fährt noch, ABER am Ende Gelb -> Rot -> Safety Rot
            time_left = timer_total_duration_red - timer_elapsed

            # Die letzten 4s (TIME_SAFETY_PRE_GREEN) sind Safety-Rot (Autos Rot)
            if time_left <= TIME_SAFETY_PRE_GREEN:
                c_red, c_yellow, c_green = 1, 0, 0
            # Davor TIME_CAR_YELLOW lang Gelb
            elif time_left <= (TIME_SAFETY_PRE_GREEN + TIME_CAR_YELLOW):
                c_red, c_yellow, c_green = 0, 1, 0  # Gelb
            else:
                c_red, c_yellow, c_green = 0, 0, 1  # Grün

        elif current_state == STATE_SAFETY_1:
            # Hier haben Autos ROT und Fußgänger noch ROT
            c_red, c_yellow, c_green = 1, 0, 0

        elif current_state == STATE_GREEN:
            # Fußgänger Grün, Auto Rot
            p_red, p_green = 0, 1
            c_red, c_yellow, c_green = 1, 0, 0

        elif current_state == STATE_CLEARANCE:
            # Fußgänger Rot, Auto Rot -> Rot/Gelb
            p_red, p_green = 1, 0  # Mensch Rot

            time_passed = now - clearance_start_time
            time_left_clearance = TIME_CLEARANCE - time_passed

            # Letzte 1.5s: Auto Rot-Gelb
            if time_left_clearance < TIME_CAR_RED_YELLOW:
                c_red, c_yellow, c_green = 1, 1, 0  # Rot+Gelb
            else:
                c_red, c_yellow, c_green = 1, 0, 0  # Rot

        elif current_state == STATE_TRAM:
            # T=0-3s: Gelb, T=3-5s: Rot
            # timer_elapsed läuft von 0 bis 5000
            if timer_elapsed < TIME_TRAM_YELLOW:
                # Autos Gelb
                c_red, c_yellow, c_green = 0, 1, 0
            else:
                # Autos Rot ("Buffer")
                c_red, c_yellow, c_green = 1, 0, 0
            
            # Fußgänger Rot
            p_red, p_green = 1, 0

        # Update senden / Empfangen
        if ESP_AVAILABLE and esp:
            # 1. Bildschirminhalt an ESP senden (Licht)
            # Sende Update bei Änderung ODER alle 2 Sekunden (Heartbeat/Sync)
            current_values = (p_red, p_green, c_red, c_yellow, c_green)
            if current_values != last_esp_values or (now % 2000 < dt):
                esp.update_leds(*current_values)
                last_esp_values = current_values

            # 2. Sensordaten empfangen (Personenanzahl)
            sensor_count = esp.read_sensor_data()
            if sensor_count is not None:
                # Sensor überschreibt manuelle Steuerung
                person_count = min(MAX_PERSON_CAP, sensor_count)

        # ==========================================
        # BILDSCHIRM AUSGABE
        # ==========================================
        screen.fill((0, 0, 0))

        housing_rect = images['housing'].get_rect(center=(CENTER_X, CENTER_Y))
        screen.blit(images['housing'], housing_rect)

        pos_rot = (CENTER_X, CENTER_Y + OFFSET_ROT_Y)
        pos_gruen = (CENTER_X, CENTER_Y + OFFSET_GRUEN_Y)
        pos_tram = (CENTER_X, CENTER_Y + OFFSET_TRAM_Y)

        # Ampelmännchen zeichnen
        if p_green == 1:
            screen.blit(images['red_off'], images['red_off'].get_rect(center=pos_rot))
            screen.blit(images['green_on'], images['green_on'].get_rect(center=pos_gruen))
        else:
            screen.blit(images['red_on'], images['red_on'].get_rect(center=pos_rot))
            screen.blit(images['green_off'], images['green_off'].get_rect(center=pos_gruen))

        if current_state == STATE_TRAM:
            tram_rect = images['tram'].get_rect(center=pos_tram)
            screen.blit(images['tram'], tram_rect)
            # Countdown Ring (Weiß)
            draw_led_ring(screen, visual_active_leds, VISUAL_LED_COUNT, STATE_TRAM, 255)

        elif current_state == STATE_CLEARANCE:
            draw_led_ring(screen, VISUAL_LED_COUNT, VISUAL_LED_COUNT, STATE_CLEARANCE, clearance_alpha)
            time_left = TIME_CLEARANCE - (now - clearance_start_time)
            draw_countdown_timer(screen, time_left)

        elif current_state == STATE_GREEN:
            # Wenn Tram aktiv, zusätzlich Tram-Icon anzeigen (Atemanimation)
            if tram_active:
                # Atemanimation: Sinus von Zeit
                # now ist ms. Periode z.B. 2s = 2000ms -> now * (2pi/2000)
                # Modifiziert für min. 20% Helligkeit (ca. 50 alpha) bis 255
                breath_alpha = int(153 + 102 * math.sin(now * 0.003))
                tram_surf = images['tram'].copy()
                tram_surf.set_alpha(breath_alpha)
                tram_rect = tram_surf.get_rect(center=pos_tram)
                screen.blit(tram_surf, tram_rect)

            # Einfacher weißer Ring
            draw_led_ring(screen, visual_active_leds, VISUAL_LED_COUNT, STATE_GREEN, 255)

        elif current_state == STATE_RED:
            draw_crowd_image(screen, person_count)
            draw_led_ring(screen, visual_active_leds, VISUAL_LED_COUNT, STATE_RED, 255)

        elif current_state == STATE_SAFETY_1:
            draw_crowd_image(screen, person_count)
            draw_led_ring(screen, VISUAL_LED_COUNT, VISUAL_LED_COUNT, STATE_RED, 255)

        elif current_state == STATE_IDLE:
            draw_crowd_image(screen, person_count)
            draw_led_ring(screen, 0, VISUAL_LED_COUNT, STATE_IDLE, 255)

        pygame.display.flip()

    if ESP_AVAILABLE and esp:
        esp.close()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()