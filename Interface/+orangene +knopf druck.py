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

# 1. PERSONEN LOGIK
MAX_PERSON_CAP = 8      
MAX_VISUAL_PERSONS = 8   
ADD_LEDS_PER_PERSON = 0.5  

# 2. LED ANZAHL
BASE_LEDS_GREEN = 24     
TOTAL_LEDS_RED   = 26    
MAX_LEDS_LIMIT = 30      

# 3. BONUS PUNKTE (Orange)
BONUS_ORANGE_LEDS_COUNT = 6     

# 4. GESCHWINDIGKEIT
SECONDS_PER_LED_GREEN = 0.5  
SECONDS_PER_LED_RED   = 0.3  

# --- PULSIEREN EINSTELLUNGEN ---
PULSE_SPEED = 0.004       
PULSE_ALPHA_MIN = 80      
PULSE_ALPHA_MAX = 255     

# 5. OPTIK
TIMER_FONT_SIZE = 280     
ORIGINAL_LED_RADIUS = 235  
ORIGINAL_DOT_SIZE   = 20
WAITING_ICON_SCALE = 0.22 
SNAIL_ICON_SCALE = 0.07  

# 6. LOGIK
CLEARANCE_TIME_MS = 4000 
TIME_FACTOR_SLOW = 0.7   
CROWD_BONUS_FACTOR = 0.2 

# 7. POSITIONIERUNG
OFFSET_ROT_Y   = -230  
OFFSET_GRUEN_Y = 230   
OFFSET_RING_Y  = -2    
OFFSET_TRAM_Y  = -2    

# 8. FARBEN
COLOR_LED_ON  = (255, 255, 255)  
COLOR_LED_OFF = (40, 40, 40)     
COLOR_CLEARANCE = (255, 50, 50) 
COLOR_WALKER = (255, 255, 255)
COLOR_BONUS_ORANGE = (255, 140, 0) 

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
waiting_images = [] 
game_font = None 

# ZUSTÄNDE
STATE_IDLE = "IDLE"           # Wartet auf Knopfdruck
STATE_GREEN = "GREEN"         
STATE_RED = "RED"             
STATE_CLEARANCE = "CLEARANCE" 
STATE_TRAM = "TRAM"           

def debug_log(message):
    print(f"[DEBUG] {message}", flush=True)

def load_and_scale_image(path, scale=SCALE_FACTOR):
    try:
        if not os.path.exists(path):
            if "tram" in path or "waiting" in path or "snail" in path: return None 
            else: raise FileNotFoundError(f"Datei fehlt: {path}")

        img = pygame.image.load(path).convert_alpha()
        new_width = int(img.get_width() * scale)
        new_height = int(img.get_height() * scale)
        return pygame.transform.smoothscale(img, (new_width, new_height))
    except Exception as e:
        debug_log(f"Fehler bei {path}: {e}")
        sys.exit()

def load_images():
    global game_font, waiting_images
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
    
    images['snail_white'] = load_and_scale_image(os.path.join(asset_dir, 'snail_white.png'), scale=SNAIL_ICON_SCALE)
    images['snail_orange'] = load_and_scale_image(os.path.join(asset_dir, 'snail_orange.png'), scale=SNAIL_ICON_SCALE)

    for i in range(1, MAX_VISUAL_PERSONS + 1):
        filename = f"waiting_{i}.png"
        full_path = os.path.join(asset_dir, filename)
        img = load_and_scale_image(full_path, scale=WAITING_ICON_SCALE)
        if img: waiting_images.append(img)
        else: waiting_images.append(None)

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

def draw_crowd_image(screen, person_count):
    if person_count <= 0: return
    image_index = min(person_count, MAX_VISUAL_PERSONS) - 1
    
    if waiting_images and 0 <= image_index < len(waiting_images):
        current_img = waiting_images[image_index]
        if current_img:
            rect = current_img.get_rect(center=(CENTER_X, CENTER_Y + OFFSET_RING_Y))
            screen.blit(current_img, rect)
        else:
            pygame.draw.circle(screen, (100, 100, 100), (CENTER_X, CENTER_Y + OFFSET_RING_Y), 30)
            text = str(person_count)
            game_font.render_to(screen, (CENTER_X-10, CENTER_Y+OFFSET_RING_Y-10), text, (255, 255, 255))

def draw_snail(screen, alpha, color_variant='white'):
    if color_variant == 'orange':
        snail_img = images.get('snail_orange')
    else:
        snail_img = images.get('snail_white')
        
    if snail_img:
        temp_snail = snail_img.copy()
        temp_snail.set_alpha(alpha)
        rect = temp_snail.get_rect(center=(CENTER_X, CENTER_Y + OFFSET_RING_Y))
        screen.blit(temp_snail, rect)

def draw_countdown_timer(screen, remaining_ms):
    seconds = math.ceil(remaining_ms / 1000)
    if seconds < 1: seconds = 1 
    text = str(seconds)
    text_rect = game_font.get_rect(text)
    x = CENTER_X - (text_rect.width // 2)
    y = CENTER_Y + OFFSET_RING_Y - (text_rect.height // 2)
    game_font.render_to(screen, (x, y), text, (255, 255, 255))

def draw_led_ring(screen, active_leds, total_leds, state, breathing_alpha=255, is_slow_mode=False, orange_count=0):
    ring_center_y = CENTER_Y + OFFSET_RING_Y
    
    current_dot_size = DOT_SIZE_BASE
    if total_leds > 60:
        factor = 60 / total_leds
        current_dot_size = max(2, int(DOT_SIZE_BASE * factor))
    
    surf_size = (current_dot_size * 2) + 4
    center_offset = surf_size // 2

    for i in range(total_leds):
        angle = math.radians(-90 + (360 / total_leds) * i)
        x_int = int(CENTER_X + LED_RADIUS * math.cos(angle))
        y_int = int(ring_center_y + LED_RADIUS * math.sin(angle))
        
        is_lit = False
        is_orange_bonus = False 
        current_color = COLOR_LED_OFF

        # --- LOGIK ---
        if state == STATE_GREEN:
            leds_gone = total_leds - active_leds
            shifted_i = (i - 1) % total_leds
            
            if shifted_i >= leds_gone:
                is_lit = True
                current_color = COLOR_LED_ON
            
            if is_slow_mode:
                if active_leds > 0:
                    if i > 0 and i <= leds_gone and i <= BONUS_ORANGE_LEDS_COUNT:
                        is_lit = True
                        is_orange_bonus = True
                        current_color = COLOR_BONUS_ORANGE
                else:
                    orange_gone = BONUS_ORANGE_LEDS_COUNT - orange_count
                    if i > orange_gone and i <= BONUS_ORANGE_LEDS_COUNT:
                        is_lit = True
                        is_orange_bonus = True
                        current_color = COLOR_BONUS_ORANGE

        elif state == STATE_RED:
            # Füll-Effekt bei Rot
            if i < active_leds: 
                is_lit = True
                current_color = COLOR_LED_ON
                
        elif state == STATE_TRAM:
            if i < active_leds: 
                is_lit = True
                current_color = COLOR_LED_ON
        
        elif state == STATE_CLEARANCE:
            is_lit = True
            current_color = COLOR_CLEARANCE
            
        elif state == STATE_IDLE:
            # Im Idle Modus leuchtet nichts, nur der Hintergrund (Grau)
            is_lit = False

        # --- ZEICHNEN ---
        if is_lit:
            use_fading = False
            
            if state == STATE_GREEN and is_slow_mode and is_orange_bonus:
                use_fading = True
            elif state == STATE_CLEARANCE:
                use_fading = True
            
            if use_fading:
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
    debug_log("Starte Programm...")
    pygame.init()
    pygame.display.set_mode((100, 100))
    load_images()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Traffic Light Control")
    
    clock = pygame.time.Clock()
    
    # STARTZUSTAND: IDLE (Warten auf 'G')
    current_state = STATE_IDLE 
    led_counter = 0
    current_total_leds = TOTAL_LEDS_RED 
    
    timer_accumulator = 0 
    clearance_start_time = 0
    tram_display_timer = 0
    person_count = 0 
    
    slow_mode_active = False
    current_orange_leds = BONUS_ORANGE_LEDS_COUNT
    orange_timer_accumulator = 0
    
    running = True
    while running:
        dt = clock.tick(60) 
        now = pygame.time.get_ticks()
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            
            if event.type == pygame.KEYDOWN:
                # --- INTERAKTION 'G': STARTET DEN ZYKLUS ---
                if event.key == pygame.K_g:
                    if current_state == STATE_IDLE:
                        debug_log("Knopf gedrückt! Zyklus startet.")
                        current_state = STATE_RED
                        current_total_leds = TOTAL_LEDS_RED
                        led_counter = 0
                        timer_accumulator = 0
                
                if event.key == pygame.K_t: 
                    current_state = STATE_TRAM
                    tram_display_timer = pygame.time.get_ticks()
                
                if event.key == pygame.K_SPACE:
                    if current_state == STATE_GREEN:
                        slow_mode_active = not slow_mode_active
                        if slow_mode_active:
                            current_orange_leds = BONUS_ORANGE_LEDS_COUNT
                            orange_timer_accumulator = 0
                        else:
                            current_orange_leds = 0
                
                if event.key == pygame.K_UP: 
                    person_count = min(MAX_PERSON_CAP, person_count + 1)
                
                if event.key == pygame.K_DOWN: 
                    person_count = max(0, person_count - 1)

        # ZEIT-FAKTOR
        current_time_factor = 1.0 
        if current_state == STATE_RED:
            current_time_factor = 1.0 + ((person_count / 5) * CROWD_BONUS_FACTOR)

        # FADING
        breath_alpha = 255
        if current_state == STATE_GREEN and slow_mode_active:
             pulse = (math.sin(now * PULSE_SPEED) + 1) / 2 
             breath_alpha = int(PULSE_ALPHA_MIN + ((PULSE_ALPHA_MAX - PULSE_ALPHA_MIN) * pulse)) 
        
        clearance_alpha = 255
        if current_state == STATE_CLEARANCE:
            clearance_alpha = int(128 + 127 * math.sin(now * 0.020))

        if current_state == STATE_IDLE:
            # Im Idle passiert nichts außer Warten
            pass

        elif current_state == STATE_TRAM:
            if now - tram_display_timer > 2000:
                current_state = STATE_IDLE # Tram vorbei -> Idle
                # Oder soll Tram zu Rot führen? Meistens reset. 
                # Hier zurück zu Idle für Konsistenz.
                led_counter = 0

        elif current_state == STATE_CLEARANCE:
            if now - clearance_start_time > CLEARANCE_TIME_MS:
                # ZYKLUS ENDE -> ZURÜCK ZU IDLE
                current_state = STATE_IDLE
                current_total_leds = TOTAL_LEDS_RED 
                led_counter = 0
                person_count = 0 
                slow_mode_active = False 
                debug_log("Zyklus beendet. Warte auf Knopfdruck (G).")

        else:
            timer_accumulator += dt * current_time_factor
            time_threshold = MS_PER_LED_GREEN if current_state == STATE_GREEN else MS_PER_LED_RED
            
            if timer_accumulator >= time_threshold:
                timer_accumulator -= time_threshold
                
                if current_state == STATE_GREEN:
                    if led_counter > 0:
                        led_counter -= 1
                    else:
                        if not slow_mode_active:
                             current_state = STATE_CLEARANCE
                             clearance_start_time = now
                             current_total_leds = current_total_leds 
                             led_counter = 0
                             timer_accumulator = 0
                
                elif current_state == STATE_RED:
                    led_counter += 1
                    if led_counter > TOTAL_LEDS_RED:
                        current_state = STATE_GREEN
                        
                        bonus_leds_float = person_count * ADD_LEDS_PER_PERSON
                        bonus_leds = int(round(bonus_leds_float))
                        
                        total_green = BASE_LEDS_GREEN + bonus_leds
                        if total_green > MAX_LEDS_LIMIT: total_green = MAX_LEDS_LIMIT
                        
                        current_total_leds = total_green
                        led_counter = total_green
                        timer_accumulator = 0
                        slow_mode_active = False 
                        current_orange_leds = BONUS_ORANGE_LEDS_COUNT

            if current_state == STATE_GREEN and slow_mode_active and led_counter == 0:
                orange_timer_accumulator += dt
                if orange_timer_accumulator >= MS_PER_LED_GREEN:
                    orange_timer_accumulator -= MS_PER_LED_GREEN
                    current_orange_leds -= 1
                    
                    if current_orange_leds < 0:
                        current_state = STATE_CLEARANCE
                        clearance_start_time = now
                        current_total_leds = current_total_leds 
                        led_counter = 0
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
            # Bei IDLE, RED, CLEARANCE, TRAM: Rot ist an
            screen.blit(images['red_on'], images['red_on'].get_rect(center=pos_rot))
            screen.blit(images['green_off'], images['green_off'].get_rect(center=pos_gruen))

        if current_state == STATE_TRAM:
            tram_rect = images['tram'].get_rect(center=pos_tram)
            screen.blit(images['tram'], tram_rect)
            draw_led_ring(screen, TOTAL_LEDS_RED, TOTAL_LEDS_RED, STATE_TRAM, 255)

        elif current_state == STATE_CLEARANCE:
            draw_led_ring(screen, current_total_leds, current_total_leds, STATE_CLEARANCE, clearance_alpha)
            time_left = CLEARANCE_TIME_MS - (now - clearance_start_time)
            draw_countdown_timer(screen, time_left)

        elif current_state == STATE_GREEN:
            if slow_mode_active:
                if led_counter > 0:
                    draw_snail(screen, breath_alpha, 'white')
                elif current_orange_leds > 0:
                    draw_snail(screen, breath_alpha, 'orange')
                
            draw_led_ring(screen, led_counter, current_total_leds, STATE_GREEN, 
                          breathing_alpha=breath_alpha, 
                          is_slow_mode=slow_mode_active,
                          orange_count=current_orange_leds)
            
        elif current_state == STATE_RED:
            draw_crowd_image(screen, person_count)
            draw_led_ring(screen, led_counter, TOTAL_LEDS_RED, STATE_RED, 255)
            
        elif current_state == STATE_IDLE:
            # Im Idle Modus zeigen wir den Crowd-Zähler (optional) und den leeren Ring
            draw_crowd_image(screen, person_count)
            draw_led_ring(screen, 0, TOTAL_LEDS_RED, STATE_IDLE, 255)

        pygame.display.flip() 

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()