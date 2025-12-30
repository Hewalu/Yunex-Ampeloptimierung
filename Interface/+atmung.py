import pygame
import pygame.freetype 
from pygame import gfxdraw
import math
import sys
import os

# ==========================================
#      KONFIGURATION
# ==========================================

SCALE_FACTOR = 0.3   

# 1. PERSONEN LOGIK (NEU)
MAX_PERSON_CAP = 15      # Maximal 15 Personen werden erkannt/visualisiert
ADD_LEDS_PER_PERSON = 2  # Pro Person +2 Punkte bei Grün

# 2. LED ANZAHL
BASE_LEDS_GREEN = 12     
TOTAL_LEDS_RED   = 34    
MAX_LEDS_LIMIT = 34      

# 3. GESCHWINDIGKEIT
SECONDS_PER_LED_GREEN = 1.0  
SECONDS_PER_LED_RED   = 0.3  

# 4. OPTIK
BASE_WALK_SPEED = 0.015  
TIMER_FONT_SIZE = 280     
ORIGINAL_LED_RADIUS = 235  
ORIGINAL_DOT_SIZE   = 20   

# 5. LOGIK
CLEARANCE_TIME_MS = 4000 
TIME_FACTOR_SLOW = 0.7   
CROWD_BONUS_FACTOR = 0.2 

# 6. POSITIONIERUNG
OFFSET_ROT_Y   = -230  
OFFSET_GRUEN_Y = 230   
OFFSET_RING_Y  = -2    
OFFSET_TRAM_Y  = -2    

# 7. FARBEN
COLOR_LED_ON  = (255, 255, 255)  
COLOR_LED_OFF = (60, 60, 60)
COLOR_CLEARANCE = (255, 50, 50) 
COLOR_CROWD_BLOB = (200, 200, 200) 
COLOR_WALKER = (255, 255, 255) 

# ==========================================
# SYSTEM CODE
# ==========================================

MS_PER_LED_GREEN = int(SECONDS_PER_LED_GREEN * 1000)
MS_PER_LED_RED   = int(SECONDS_PER_LED_RED * 1000)

WIDTH, HEIGHT = 0, 0 
CENTER_X, CENTER_Y = 0, 0
LED_RADIUS = 0
DOT_SIZE_BASE = 0
images = {}
game_font = None 

STATE_GREEN = "GREEN"         
STATE_RED = "RED"             
STATE_CLEARANCE = "CLEARANCE" 
STATE_TRAM = "TRAM"           

def debug_log(message):
    print(f"[DEBUG] {message}", flush=True)

def load_and_scale_image(path, scale=SCALE_FACTOR):
    try:
        if not os.path.exists(path):
            if "tram" in path:
                return pygame.Surface((100, 100), pygame.SRCALPHA)
            else:
                raise FileNotFoundError(f"Datei fehlt: {path}")

        img = pygame.image.load(path).convert_alpha()
        new_width = int(img.get_width() * scale)
        new_height = int(img.get_height() * scale)
        return pygame.transform.smoothscale(img, (new_width, new_height))
    except Exception as e:
        debug_log(f"Fehler bei {path}: {e}")
        sys.exit()

def load_images():
    global game_font
    script_dir = os.path.dirname(os.path.abspath(__file__))
    asset_dir = os.path.join(script_dir, "assets")
    
    if not os.path.exists(asset_dir):
        debug_log("Assets Ordner fehlt!")
        sys.exit()
    
    images['housing'] = load_and_scale_image(os.path.join(asset_dir, 'gehaeuse.png'))
    images['red_on'] = load_and_scale_image(os.path.join(asset_dir, 'mann_rot_an.png'))
    images['red_off'] = load_and_scale_image(os.path.join(asset_dir, 'mann_rot_aus.png'))
    images['green_on'] = load_and_scale_image(os.path.join(asset_dir, 'mann_gruen_an.png'))
    images['green_off'] = load_and_scale_image(os.path.join(asset_dir, 'mann_gruen_aus.png'))
    images['tram'] = load_and_scale_image(os.path.join(asset_dir, 'tram.png')) 

    global WIDTH, HEIGHT, CENTER_X, CENTER_Y, LED_RADIUS, DOT_SIZE_BASE
    WIDTH = images['housing'].get_width()
    HEIGHT = images['housing'].get_height()
    CENTER_X = WIDTH // 2
    CENTER_Y = HEIGHT // 2
    
    LED_RADIUS = int(ORIGINAL_LED_RADIUS * SCALE_FACTOR)
    DOT_SIZE_BASE = int(ORIGINAL_DOT_SIZE * SCALE_FACTOR)
    if DOT_SIZE_BASE < 2: DOT_SIZE_BASE = 2
    
    font_size = int(TIMER_FONT_SIZE * SCALE_FACTOR)
    game_font = pygame.freetype.SysFont("Arial", font_size, bold=True)

# --- ZEICHNEN ---

def draw_walking_man(screen, time_factor, ticks):
    anim_speed = BASE_WALK_SPEED * time_factor 
    cycle = math.sin(ticks * anim_speed)
    
    center_x = CENTER_X
    center_y = CENTER_Y + OFFSET_RING_Y
    size = 40 * SCALE_FACTOR 
    
    head_pos = (center_x, center_y - size)
    hip_pos = (center_x, center_y + size * 0.2)
    leg_swing = size * 0.8 * cycle
    knee_bend = size * 0.2 * abs(cycle)
    foot_l = (center_x - leg_swing, center_y + size * 1.5 - knee_bend)
    foot_r = (center_x + leg_swing, center_y + size * 1.5 - knee_bend)
    arm_swing = size * 0.6 * cycle
    hand_l = (center_x + arm_swing, center_y) 
    hand_r = (center_x - arm_swing, center_y)
    shoulder = (center_x, center_y - size * 0.5)

    thickness = max(2, int(5 * SCALE_FACTOR))
    color = COLOR_WALKER
    
    pygame.draw.circle(screen, color, (int(head_pos[0]), int(head_pos[1])), int(size*0.4))
    pygame.draw.line(screen, color, (int(head_pos[0]), int(head_pos[1]+size*0.4)), (int(hip_pos[0]), int(hip_pos[1])), thickness)
    pygame.draw.line(screen, color, (int(hip_pos[0]), int(hip_pos[1])), (int(foot_l[0]), int(foot_l[1])), thickness)
    pygame.draw.line(screen, color, (int(hip_pos[0]), int(hip_pos[1])), (int(foot_r[0]), int(foot_r[1])), thickness)
    pygame.draw.line(screen, color, (int(shoulder[0]), int(shoulder[1])), (int(hand_l[0]), int(hand_l[1])), thickness)
    pygame.draw.line(screen, color, (int(shoulder[0]), int(shoulder[1])), (int(hand_r[0]), int(hand_r[1])), thickness)

    if time_factor > 0.5:
        wind_offset_x = -size * 1.5
        for i in range(3):
            slide = (ticks * 0.05 + i * 20) % 30
            wind_y = center_y - size + (i * size * 0.6)
            wind_start = center_x + wind_offset_x + slide
            wind_end = wind_start - (size * 0.5)
            start_pos = (int(wind_start), int(wind_y))
            end_pos = (int(wind_end), int(wind_y))
            pygame.draw.line(screen, color, start_pos, end_pos, int(thickness*0.6))

def draw_crowd_blob(screen, person_count, ticks):
    if person_count <= 0: return
    
    # Radius so berechnen, dass er nicht in die LEDs reinragt
    max_possible_radius = LED_RADIUS - DOT_SIZE_BASE - 15
    
    # HIER IST DIE ÄNDERUNG:
    # Wir teilen durch MAX_PERSON_CAP (15) statt durch 50.
    # Das heißt bei 15 Personen ist der Faktor 1.0 (100%).
    growth_factor = min(person_count / float(MAX_PERSON_CAP), 1.0)
    
    # Mindestgröße 20 Pixel, maximal max_possible_radius
    current_radius = int(20 * SCALE_FACTOR + (max_possible_radius * growth_factor))
    
    x, y = CENTER_X, CENTER_Y + OFFSET_RING_Y
    
    # Breathing Animation
    pulse = (math.sin(ticks * 0.003) + 1) / 2 
    alpha = int(150 + (80 * pulse))
    
    blob_surf = pygame.Surface((current_radius*2, current_radius*2), pygame.SRCALPHA)
    pygame.draw.circle(blob_surf, (*COLOR_CROWD_BLOB, alpha), (current_radius, current_radius), current_radius)
    screen.blit(blob_surf, (x - current_radius, y - current_radius))

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
        factor = 60 / total_leds
        current_dot_size = max(2, int(DOT_SIZE_BASE * factor))
    
    for i in range(total_leds):
        angle = math.radians(-90 + (360 / total_leds) * i)
        x_int = int(CENTER_X + LED_RADIUS * math.cos(angle))
        y_int = int(ring_center_y + LED_RADIUS * math.sin(angle))
        
        is_lit = False
        current_color = COLOR_LED_OFF

        if state == STATE_GREEN:
            leds_gone = total_leds - active_leds
            if i >= leds_gone: 
                is_lit = True
                current_color = COLOR_LED_ON
        elif state == STATE_RED:
            if i < active_leds: 
                is_lit = True
                current_color = COLOR_LED_ON
        elif state == STATE_CLEARANCE:
            is_lit = True
            current_color = COLOR_CLEARANCE
        elif state == STATE_TRAM:
            is_lit = True
            current_color = COLOR_LED_ON

        if is_lit:
            if breathing_alpha < 255 or state == STATE_CLEARANCE:
                target_surface = pygame.Surface((current_dot_size*2, current_dot_size*2), pygame.SRCALPHA)
                r, g, b = current_color
                pygame.draw.circle(target_surface, (r, g, b, breathing_alpha), (current_dot_size, current_dot_size), current_dot_size)
                screen.blit(target_surface, (x_int-current_dot_size, y_int-current_dot_size))
            else:
                gfxdraw.filled_circle(screen, x_int, y_int, current_dot_size, current_color)
                gfxdraw.aacircle(screen, x_int, y_int, current_dot_size, current_color)
        else:
            gfxdraw.filled_circle(screen, x_int, y_int, current_dot_size, COLOR_LED_OFF)
            gfxdraw.aacircle(screen, x_int, y_int, current_dot_size, COLOR_LED_OFF)

def main():
    debug_log("Starte Programm...")
    pygame.init()
    pygame.display.set_mode((100, 100))
    load_images()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Traffic Light Control")
    
    clock = pygame.time.Clock()
    
    current_state = STATE_RED 
    led_counter = 0
    current_total_leds = TOTAL_LEDS_RED 
    
    timer_accumulator = 0 
    clearance_start_time = 0
    tram_display_timer = 0
    person_count = 0 
    
    running = True
    while running:
        dt = clock.tick(60) 
        now = pygame.time.get_ticks()
        
        keys = pygame.key.get_pressed()
        slow_walker_detected = keys[pygame.K_SPACE] 
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_t: 
                    current_state = STATE_TRAM
                    tram_display_timer = pygame.time.get_ticks()
                
                if event.key == pygame.K_UP: 
                    # Begrenzen auf MAX_PERSON_CAP
                    person_count = min(MAX_PERSON_CAP, person_count + 1)
                
                if event.key == pygame.K_DOWN: 
                    person_count = max(0, person_count - 1)

        # ZEIT-FAKTOR
        current_time_factor = 1.0 
        if current_state == STATE_GREEN:
            if slow_walker_detected: current_time_factor = TIME_FACTOR_SLOW
        elif current_state == STATE_RED:
            current_time_factor = 1.0 + ((person_count / 5) * CROWD_BONUS_FACTOR)

        breath_alpha = 255
        if current_state == STATE_GREEN and slow_walker_detected:
             breath_alpha = int(155 + 100 * math.sin(now * 0.005)) 

        if current_state == STATE_TRAM:
            if now - tram_display_timer > 2000:
                current_state = STATE_RED 
                current_total_leds = TOTAL_LEDS_RED 
                led_counter = 0

        elif current_state == STATE_CLEARANCE:
            if now - clearance_start_time > CLEARANCE_TIME_MS:
                current_state = STATE_RED
                current_total_leds = TOTAL_LEDS_RED 
                led_counter = 0
                person_count = 0 
                debug_log("Reset: Personenanzahl auf 0.")

        else:
            timer_accumulator += dt * current_time_factor
            time_threshold = MS_PER_LED_GREEN if current_state == STATE_GREEN else MS_PER_LED_RED
            
            if timer_accumulator >= time_threshold:
                timer_accumulator -= time_threshold
                
                if current_state == STATE_GREEN:
                    led_counter -= 1
                    if led_counter < 0:
                        current_state = STATE_CLEARANCE
                        clearance_start_time = now
                        led_counter = 0
                        timer_accumulator = 0
                
                elif current_state == STATE_RED:
                    led_counter += 1
                    if led_counter > TOTAL_LEDS_RED:
                        current_state = STATE_GREEN
                        
                        bonus_leds = person_count * ADD_LEDS_PER_PERSON
                        total_green = BASE_LEDS_GREEN + bonus_leds
                        
                        if total_green > MAX_LEDS_LIMIT:
                            total_green = MAX_LEDS_LIMIT
                        
                        current_total_leds = total_green
                        led_counter = total_green
                        timer_accumulator = 0

        # ZEICHNEN
        screen.fill((0,0,0)) 
        
        housing_rect = images['housing'].get_rect(center=(CENTER_X, CENTER_Y))
        screen.blit(images['housing'], housing_rect)
        
        pos_rot = (CENTER_X, CENTER_Y + OFFSET_ROT_Y)
        pos_gruen = (CENTER_X, CENTER_Y + OFFSET_GRUEN_Y)
        pos_tram = (CENTER_X, CENTER_Y + OFFSET_TRAM_Y)

        if current_state == STATE_GREEN:
            screen.blit(images['red_off'], images['red_off'].get_rect(center=pos_rot))
            screen.blit(images['green_on'], images['green_on'].get_rect(center=pos_gruen))
        else:
            screen.blit(images['red_on'], images['red_on'].get_rect(center=pos_rot))
            screen.blit(images['green_off'], images['green_off'].get_rect(center=pos_gruen))

        if current_state == STATE_TRAM:
            tram_rect = images['tram'].get_rect(center=pos_tram)
            screen.blit(images['tram'], tram_rect)
            draw_led_ring(screen, TOTAL_LEDS_RED, TOTAL_LEDS_RED, STATE_TRAM, 255)

        elif current_state == STATE_CLEARANCE:
            flash_alpha = int(128 + 127 * math.sin(now * 0.020)) 
            draw_led_ring(screen, current_total_leds, current_total_leds, STATE_CLEARANCE, flash_alpha)
            time_left = CLEARANCE_TIME_MS - (now - clearance_start_time)
            draw_countdown_timer(screen, time_left)

        elif current_state == STATE_GREEN:
            draw_walking_man(screen, current_time_factor, now)
            draw_led_ring(screen, led_counter, current_total_leds, STATE_GREEN, breath_alpha)
            
        else: # STATE_RED
            draw_crowd_blob(screen, person_count, now)
            draw_led_ring(screen, led_counter, TOTAL_LEDS_RED, STATE_RED, 255)

        pygame.display.flip() 

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()