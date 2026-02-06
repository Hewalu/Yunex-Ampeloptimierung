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
# FIX: Damit der Ring voll startet, orientieren wir uns an der visuellen Anzahl
VISUAL_LED_COUNT = 25
BASE_LEDS_GREEN = 25  # Angepasst auf 25, damit Standard-Zeit = voller Ring ist
TOTAL_LEDS_RED = 25
MAX_LEDS_LIMIT = 35   # Limit etwas erhöht für Bonus

# 3. GESCHWINDIGKEITEN
SECONDS_PER_LED_RED = 1.0
SECONDS_PER_LED_GREEN = 0.333
SECONDS_PER_LED_GREEN_SLOW = 0.5

# 4. FESTE PHASEN (in Millisekunden)
TIME_SAFETY_PRE_GREEN = 3000
TIME_CLEARANCE = 11000
TIME_CAR_YELLOW = 3000
TIME_CAR_RED_YELLOW = 1500

# Tram Zeiten
TIME_TRAM_PRE_GREEN = 5000
TIME_TRAM_GREEN_DURATION = 25000
TIME_TRAM_YELLOW = 3000

# Basis-Dauer Rotphase berechnen
DURATION_RED_BASE_MS = int(TOTAL_LEDS_RED * SECONDS_PER_LED_RED * 1000)

# 5. OPTIK / FARBEN
TIMER_FONT_SIZE = 280
ORIGINAL_LED_RADIUS = 235
ORIGINAL_DOT_SIZE = 20
WAITING_ICON_SCALE = 0.22

OFFSET_ROT_Y = -234
OFFSET_GRUEN_Y = 230
OFFSET_RING_Y = -2
OFFSET_TRAM_Y = -2

COLOR_LED_ON = (255, 255, 255)
COLOR_LED_OFF = (40, 40, 40)
COLOR_CLEARANCE = (255, 50, 50)
COLOR_WALKER = (255, 255, 255)

# Farben für Auto-Ampel Lichter
CAR_RED_ON = (255, 30, 30)
CAR_YELLOW_ON = (255, 200, 0)
CAR_GREEN_ON = (30, 255, 30)
CAR_OFF_DIM = (50, 30, 30)

# ==========================================
# SYSTEM CODE
# ==========================================

WIDTH, HEIGHT = 0, 0 
WINDOW_WIDTH, WINDOW_HEIGHT = 0, 0 
CENTER_X, CENTER_Y = 0, 0
CENTER_X_CAR, CENTER_Y_CAR = 0, 0
TIMER_POS_X, TIMER_POS_Y = 0, 0

LED_RADIUS = 0
DOT_SIZE_BASE = 0
images = {}
waiting_images = []
game_font = None
info_font = None

# ZUSTÄNDE
STATE_IDLE = "IDLE"
STATE_RED = "RED"
STATE_SAFETY_1 = "SAFETY_1"
STATE_GREEN = "GREEN"
STATE_CLEARANCE = "CLEARANCE"
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
        print(f"[FEHLER] Bild konnte nicht geladen werden: {path}\nGrund: {e}")
        sys.exit()

def load_images():
    global game_font, info_font, waiting_images
    script_dir = os.path.dirname(os.path.abspath(__file__))
    asset_dir = os.path.join(script_dir, "assets")
    
    if not os.path.exists(asset_dir):
        print(f"[CRITICAL ERROR] Ordner 'assets' nicht gefunden im Pfad: {asset_dir}")
        sys.exit()

    images['housing'] = load_and_scale_image(os.path.join(asset_dir, 'gehaeuse.png'))
    images['red_on'] = load_and_scale_image(os.path.join(asset_dir, 'mann_rot_an.png'))
    images['red_off'] = load_and_scale_image(os.path.join(asset_dir, 'mann_rot_aus.png'))
    images['green_on'] = load_and_scale_image(os.path.join(asset_dir, 'mann_gruen_an.png'))
    images['green_off'] = load_and_scale_image(os.path.join(asset_dir, 'mann_gruen_aus.png'))
    images['tram'] = load_and_scale_image(os.path.join(asset_dir, 'tram.png'), scale=SCALE_FACTOR * 0.7)

    for i in range(1, MAX_VISUAL_PERSONS + 1):
        filename = f"waiting_{i}.png"
        full_path = os.path.join(asset_dir, filename)
        if os.path.exists(full_path):
            img = load_and_scale_image(full_path, scale=WAITING_ICON_SCALE)
            waiting_images.append(img)
        else:
            waiting_images.append(None)

    global WIDTH, HEIGHT, WINDOW_WIDTH, WINDOW_HEIGHT, CENTER_X, CENTER_Y, CENTER_X_CAR, CENTER_Y_CAR, TIMER_POS_X, TIMER_POS_Y, LED_RADIUS, DOT_SIZE_BASE
    
    if images['housing'] is None: sys.exit()

    WIDTH = images['housing'].get_width()
    HEIGHT = images['housing'].get_height()
    
    # --- LAYOUT ---
    PADDING = 120
    WINDOW_WIDTH = PADDING + WIDTH + PADDING + WIDTH + PADDING + 400 + PADDING // 2
    WINDOW_HEIGHT = HEIGHT + 150

    CENTER_Y_COMMON = WINDOW_HEIGHT // 2
    
    CENTER_X = PADDING + WIDTH // 2
    CENTER_Y = CENTER_Y_COMMON

    CENTER_X_CAR = CENTER_X + WIDTH + PADDING
    CENTER_Y_CAR = CENTER_Y_COMMON

    TIMER_POS_X = CENTER_X_CAR + WIDTH // 2 + PADDING
    TIMER_POS_Y = CENTER_Y_COMMON - 80
    
    LED_RADIUS = int(ORIGINAL_LED_RADIUS * SCALE_FACTOR)
    DOT_SIZE_BASE = max(2, int(ORIGINAL_DOT_SIZE * SCALE_FACTOR))
    
    # Technische Schriftart (Consolas oder System-Monospace)
    try:
        game_font = pygame.freetype.SysFont("Consolas", int(TIMER_FONT_SIZE * SCALE_FACTOR), bold=True)
        info_font = pygame.freetype.SysFont("Consolas", 30, bold=True)
    except:
         # Fallback falls Consolas nicht da ist
        game_font = pygame.freetype.SysFont("Courier New", int(TIMER_FONT_SIZE * SCALE_FACTOR), bold=True)
        info_font = pygame.freetype.SysFont("Courier New", 30, bold=True)

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
        # Center the text properly
        text_rect = game_font.get_rect(text)
        text_x = CENTER_X - (text_rect.width // 2)
        text_y = CENTER_Y + OFFSET_RING_Y - (text_rect.height // 2)
        game_font.render_to(screen, (text_x, text_y), text, (255, 255, 255))

def draw_countdown_timer(screen, remaining_ms):
    seconds = math.ceil(remaining_ms / 1000)
    if seconds < 1: seconds = 1
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
        angle = math.radians(-90 + (360 / total_leds) * i)
        x_int = int(CENTER_X + LED_RADIUS * math.cos(angle))
        y_int = int(ring_center_y + LED_RADIUS * math.sin(angle))

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

def draw_car_light_on_housing(screen, cx, cy, color, is_on):
    radius = 95 
    draw_color = color if is_on else CAR_OFF_DIM
    gfxdraw.filled_circle(screen, cx, cy, radius, draw_color)
    gfxdraw.aacircle(screen, cx, cy, radius, draw_color)
    # White dot reflection removed purely for aesthetics as requested
    # if is_on:
    #      pygame.draw.circle(screen, (255, 255, 255), (cx - 20, cy - 20), 10)

def main():
    os.environ['SDL_VIDEO_CENTERED'] = '1'
    debug_log("Starte Programm...")
    pygame.init()
    pygame.display.set_mode((100, 100))
    load_images()
    
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Demo Modus")

    esp = None
    if ESP_AVAILABLE:
        esp = ESPController(port=ESP_PORT)
        esp.connect()
    last_esp_values = None

    clock = pygame.time.Clock()

    current_state = STATE_IDLE
    timer_total_duration_red = DURATION_RED_BASE_MS
    timer_elapsed = 0
    green_leds_left_float = 0.0
    
    person_count = 0
    slow_mode_active = False
    visual_active_leds = 0
    tram_active = False

    # TIMER VARIABLEN
    phase_timer_ms = 0.0 
    last_light_config = (-1, -1, -1, -1, -1)
    
    # SIMULATION ZEIT
    simulated_now = 0.0 

    running = True
    while running:
        raw_dt = clock.tick(60) 
        keys = pygame.key.get_pressed()
        
        sim_speed = 2.0 if keys[pygame.K_s] else 1.0
        dt = raw_dt * sim_speed
        simulated_now += dt 

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_g and current_state == STATE_IDLE:
                    debug_log("Knopf gedrückt! Starte Rotphase.")
                    current_state = STATE_RED
                    timer_elapsed = 0
                    timer_total_duration_red = DURATION_RED_BASE_MS + TIME_SAFETY_PRE_GREEN
                    if esp: esp.set_pulsing(True)
                    phase_timer_ms = 0 

                if event.key == pygame.K_t:
                    if current_state == STATE_GREEN:
                        tram_active = True
                        # FIX: Auf vollen Ring setzen
                        green_leds_left_float = float(VISUAL_LED_COUNT)
                        slow_mode_active = False
                        phase_timer_ms = 0 
                    else:
                        current_state = STATE_TRAM
                        timer_elapsed = 0
                        tram_active = True
                        phase_timer_ms = 0 
                        
                if event.key == pygame.K_SPACE:
                    if current_state == STATE_GREEN:
                        slow_mode_active = not slow_mode_active

                if event.key == pygame.K_UP:
                    person_count = min(MAX_PERSON_CAP, person_count + 1)
                if event.key == pygame.K_DOWN:
                    person_count = max(0, person_count - 1)

        # Zeit-Faktor
        current_time_factor = 1.0
        if current_state == STATE_RED:
            current_time_factor = 1.0 + ((person_count / 5) * CROWD_BONUS_FACTOR)

        clearance_alpha = 255
        if current_state == STATE_CLEARANCE:
            clearance_alpha = int(128 + 127 * math.sin(simulated_now * 0.020))
        
        tram_breath_alpha = 255
        if tram_active:
             tram_breath_alpha = int(153 + 102 * math.sin(simulated_now * 0.003))

        # --- HARDWARE ---
        if esp:
            if esp.button_pressed:
                esp.button_pressed = False
                if current_state == STATE_IDLE:
                    current_state = STATE_RED
                    timer_elapsed = 0
                    timer_total_duration_red = DURATION_RED_BASE_MS + TIME_SAFETY_PRE_GREEN
                    esp.set_pulsing(True)
                    phase_timer_ms = 0
            
            if esp.button2_pressed:
                esp.button2_pressed = False
                slow_mode_active = not slow_mode_active

            if len(esp.sensor_values) >= 8:
                if esp.sensor_values[6] == 1 or esp.sensor_values[7] == 1:
                    if not tram_active:
                        if current_state == STATE_GREEN:
                             tram_active = True
                             green_leds_left_float = float(VISUAL_LED_COUNT)
                             slow_mode_active = False
                             phase_timer_ms = 0
                        elif current_state != STATE_TRAM:
                            current_state = STATE_TRAM
                            timer_elapsed = 0
                            tram_active = True
                            phase_timer_ms = 0

        # --- STATE MACHINE ---
        if current_state == STATE_IDLE:
            if person_count > 0:
                current_state = STATE_RED
                timer_elapsed = 0
                timer_total_duration_red = DURATION_RED_BASE_MS + TIME_SAFETY_PRE_GREEN
                phase_timer_ms = 0
                if esp: esp.set_pulsing(True)

        elif current_state == STATE_TRAM:
            timer_elapsed += dt
            ratio = timer_elapsed / TIME_TRAM_PRE_GREEN
            leds_visible_ratio = 1.0 - ratio
            if leds_visible_ratio < 0: leds_visible_ratio = 0
            visual_active_leds = int(leds_visible_ratio * VISUAL_LED_COUNT)

            if timer_elapsed >= TIME_TRAM_PRE_GREEN:
                current_state = STATE_GREEN
                timer_elapsed = 0
                # FIX: Vollen Ring nutzen
                green_leds_left_float = float(VISUAL_LED_COUNT) 
                slow_mode_active = False

        elif current_state == STATE_RED:
            timer_elapsed += dt * current_time_factor
            ratio = timer_elapsed / timer_total_duration_red
            if ratio > 1: ratio = 1
            visual_active_leds = int(ratio * VISUAL_LED_COUNT)

            if timer_elapsed >= timer_total_duration_red:
                current_state = STATE_GREEN
                timer_elapsed = 0
                if esp: esp.set_pulsing(False)
                
                # FIX: Hier wird nun VISUAL_LED_COUNT als Basis genommen
                # Damit startet der Ring immer VOLL (plus Bonus)
                bonus_leds = person_count * ADD_LEDS_PER_PERSON
                green_leds_left_float = float(VISUAL_LED_COUNT + bonus_leds)
                
                if green_leds_left_float > MAX_LEDS_LIMIT:
                    green_leds_left_float = float(MAX_LEDS_LIMIT)
                slow_mode_active = False

        elif current_state == STATE_SAFETY_1:
            timer_elapsed += dt
            visual_active_leds = VISUAL_LED_COUNT
            if timer_elapsed >= TIME_SAFETY_PRE_GREEN:
                current_state = STATE_GREEN
                timer_elapsed = 0
                if esp: esp.set_pulsing(False)
                # FIX: Auch hier saubere Initialisierung
                bonus_leds = person_count * ADD_LEDS_PER_PERSON
                green_leds_left_float = float(VISUAL_LED_COUNT + bonus_leds)

        elif current_state == STATE_GREEN:
            if tram_active:
                seconds_per_led = TIME_TRAM_GREEN_DURATION / 1000.0 / VISUAL_LED_COUNT
            else:
                seconds_per_led = SECONDS_PER_LED_GREEN_SLOW if slow_mode_active else SECONDS_PER_LED_GREEN
            
            ms_per_led = seconds_per_led * 1000
            green_leds_left_float -= (dt / ms_per_led)
            visual_active_leds = int(green_leds_left_float)
            
            # Clamp visual leds
            if visual_active_leds > VISUAL_LED_COUNT: visual_active_leds = VISUAL_LED_COUNT
            if visual_active_leds < 0: visual_active_leds = 0

            if green_leds_left_float <= 0:
                current_state = STATE_CLEARANCE
                timer_elapsed = 0 
                visual_active_leds = VISUAL_LED_COUNT

        elif current_state == STATE_CLEARANCE:
            timer_elapsed += dt 
            if timer_elapsed > TIME_CLEARANCE:
                current_state = STATE_IDLE
                timer_elapsed = 0
                person_count = 0
                slow_mode_active = False
                tram_active = False
                if esp: esp.set_pulsing(False)

        # --- AMPEL LOGIK ---
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
            time_left_clearance = TIME_CLEARANCE - timer_elapsed
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

        if ESP_AVAILABLE and esp:
            current_values = (p_red, p_green, c_red, c_yellow, c_green)
            if current_values != last_esp_values or (pygame.time.get_ticks() % 2000 < raw_dt):
                esp.update_leds(*current_values)
                last_esp_values = current_values
            s_val = esp.read_sensor_data()
            if s_val is not None: person_count = min(MAX_PERSON_CAP, s_val)

        # --- TIMER RESET (PHASENWECHSEL) ---
        current_light_config = (p_red, p_green, c_red, c_yellow, c_green)
        if current_light_config != last_light_config:
            # Check transitions to keep timer running:
            # 1. Car: Yellow -> Red
            _, _, last_c_r, last_c_y, last_c_g = last_light_config
            _, _, curr_c_r, curr_c_y, curr_c_g = current_light_config
            
            is_yellow_to_red = (last_c_r == 0 and last_c_y == 1 and last_c_g == 0) and \
                               (curr_c_r == 1 and curr_c_y == 0 and curr_c_g == 0)
            
            # 2. Car: Red+Yellow -> Green
            is_orange_to_green = (last_c_r == 1 and last_c_y == 1 and last_c_g == 0) and \
                                 (curr_c_r == 0 and curr_c_y == 0 and curr_c_g == 1)

            if not (is_yellow_to_red or is_orange_to_green):
                phase_timer_ms = 0
                
            last_light_config = current_light_config
        
        phase_timer_ms += dt
        phase_duration_sec = phase_timer_ms / 1000.0

        # ==========================================
        # AUSGABE
        # ==========================================
        screen.fill((0, 0, 0))

        # 1. Ampel Links
        housing_rect = images['housing'].get_rect(center=(CENTER_X, CENTER_Y))
        screen.blit(images['housing'], housing_rect)

        pos_rot = (CENTER_X, CENTER_Y + OFFSET_ROT_Y)
        pos_gruen = (CENTER_X, CENTER_Y + OFFSET_GRUEN_Y)
        pos_tram = (CENTER_X, CENTER_Y + OFFSET_TRAM_Y)

        if p_green == 1:
            screen.blit(images['red_off'], images['red_off'].get_rect(center=pos_rot))
            screen.blit(images['green_on'], images['green_on'].get_rect(center=pos_gruen))
        else:
            screen.blit(images['red_on'], images['red_on'].get_rect(center=pos_rot))
            screen.blit(images['green_off'], images['green_off'].get_rect(center=pos_gruen))

        if current_state == STATE_TRAM:
            screen.blit(images['tram'], images['tram'].get_rect(center=pos_tram))
            draw_led_ring(screen, visual_active_leds, VISUAL_LED_COUNT, STATE_TRAM, 255)
        elif current_state == STATE_CLEARANCE:
            draw_led_ring(screen, VISUAL_LED_COUNT, VISUAL_LED_COUNT, STATE_CLEARANCE, clearance_alpha)
            time_left = TIME_CLEARANCE - timer_elapsed
            draw_countdown_timer(screen, time_left)
        elif current_state == STATE_GREEN:
            if tram_active:
                tram_surf = images['tram'].copy()
                tram_surf.set_alpha(tram_breath_alpha)
                screen.blit(tram_surf, tram_surf.get_rect(center=pos_tram))
            draw_led_ring(screen, visual_active_leds, VISUAL_LED_COUNT, STATE_GREEN, 255)
        elif current_state == STATE_RED or current_state == STATE_SAFETY_1:
            draw_crowd_image(screen, person_count)
            draw_led_ring(screen, visual_active_leds, VISUAL_LED_COUNT, STATE_RED, 255)
        elif current_state == STATE_IDLE:
            draw_crowd_image(screen, person_count)
            draw_led_ring(screen, 0, VISUAL_LED_COUNT, STATE_IDLE, 255)

        # 2. Auto Ampel Mitte
        housing_rect_car = images['housing'].get_rect(center=(CENTER_X_CAR, CENTER_Y_CAR))
        screen.blit(images['housing'], housing_rect_car)

        pos_car_red = (CENTER_X_CAR, CENTER_Y_CAR + OFFSET_ROT_Y)
        pos_car_green = (CENTER_X_CAR, CENTER_Y_CAR + OFFSET_GRUEN_Y)
        pos_car_yellow = (CENTER_X_CAR, CENTER_Y_CAR) 

        draw_car_light_on_housing(screen, *pos_car_red, CAR_RED_ON, c_red)
        draw_car_light_on_housing(screen, *pos_car_yellow, CAR_YELLOW_ON, c_yellow)
        draw_car_light_on_housing(screen, *pos_car_green, CAR_GREEN_ON, c_green)

        # 3. Timer Rechts
        info_font.render_to(screen, (TIMER_POS_X, TIMER_POS_Y), "Timer:", (200, 200, 200))
        
        # Farbe Logik: Grünlich wenn Speedup, sonst Weiß
        timer_color = (100, 255, 100) if sim_speed > 1.0 else (255, 255, 255)
        
        time_str = f"{phase_duration_sec:.2f} s"
        if sim_speed > 1.0: time_str += " (2x)"

        timer_surf, _ = game_font.render(time_str, timer_color)
        scale_timer_display = 0.45
        timer_surf_scaled = pygame.transform.smoothscale(timer_surf, (int(timer_surf.get_width()*scale_timer_display), int(timer_surf.get_height()*scale_timer_display)))
        screen.blit(timer_surf_scaled, (TIMER_POS_X, TIMER_POS_Y + 40))

        if slow_mode_active:
             slow_text = "SLOW MODE"
             slow_surf, _ = info_font.render(slow_text, (77, 166, 255)) 
             screen.blit(slow_surf, (TIMER_POS_X, TIMER_POS_Y + 110))

        pygame.display.flip()

    if ESP_AVAILABLE and esp:
        esp.close()
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()