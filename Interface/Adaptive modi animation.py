import pygame
import math
import sys
import os
# NEU: Diese Spezial-Bibliothek brauchen wir für scharfe Kreise
from pygame import gfxdraw 

# ==========================================
#      KONFIGURATION
# ==========================================

SCALE_FACTOR = 0.3   

# ZEITEN
TOTAL_LEDS = 24      
SECONDS_PER_LED = 0.5 
CLEARANCE_TIME_MS = 3000 

# POSITIONIERUNG
OFFSET_ROT_Y   = -230  
OFFSET_GRUEN_Y = 230   
OFFSET_RING_Y  = -2    
OFFSET_TRAM_Y  = -2    

# OPTIK
ORIGINAL_LED_RADIUS = 235  
ORIGINAL_DOT_SIZE   = 25   

# FARBEN
COLOR_LED_ON  = (255, 255, 255)  
COLOR_LED_OFF = (60, 60, 60)
COLOR_CLEARANCE = (255, 255, 255) 

# ==========================================
# SYSTEM CODE
# ==========================================

WIDTH, HEIGHT = 0, 0 
CENTER_X, CENTER_Y = 0, 0
LED_RADIUS = 0
DOT_SIZE = 0
TICK_INTERVAL = int(SECONDS_PER_LED * 1000) 
images = {}

# ZUSTÄNDE
STATE_GREEN = "GREEN"         
STATE_RED = "RED"             
STATE_CLEARANCE = "CLEARANCE" 
STATE_TRAM = "TRAM"           

def load_and_scale_image(path, scale=SCALE_FACTOR):
    try:
        if not os.path.exists(path):
            if "tram" in path:
                print("Warnung: tram.png nicht gefunden. Mache ohne weiter.")
                surface = pygame.Surface((100, 100), pygame.SRCALPHA)
                pygame.draw.circle(surface, (255,255,255), (50,50), 40)
                return surface
            else:
                raise FileNotFoundError(path)

        img = pygame.image.load(path).convert_alpha()
        new_width = int(img.get_width() * scale)
        new_height = int(img.get_height() * scale)
        return pygame.transform.smoothscale(img, (new_width, new_height))
    except Exception as e:
        print(f"Fehler bei {path}: {e}")
        sys.exit()

def load_images():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    asset_dir = os.path.join(script_dir, "assets")
    
    print(f"Lade Bilder aus: {asset_dir}")

    images['housing'] = load_and_scale_image(os.path.join(asset_dir, 'gehaeuse.png'))
    images['red_on'] = load_and_scale_image(os.path.join(asset_dir, 'mann_rot_an.png'))
    images['red_off'] = load_and_scale_image(os.path.join(asset_dir, 'mann_rot_aus.png'))
    images['green_on'] = load_and_scale_image(os.path.join(asset_dir, 'mann_gruen_an.png'))
    images['green_off'] = load_and_scale_image(os.path.join(asset_dir, 'mann_gruen_aus.png'))
    images['tram'] = load_and_scale_image(os.path.join(asset_dir, 'tram.png')) 

    global WIDTH, HEIGHT, CENTER_X, CENTER_Y, LED_RADIUS, DOT_SIZE
    WIDTH = images['housing'].get_width()
    HEIGHT = images['housing'].get_height()
    CENTER_X = WIDTH // 2
    CENTER_Y = HEIGHT // 2
    
    LED_RADIUS = int(ORIGINAL_LED_RADIUS * SCALE_FACTOR)
    DOT_SIZE = int(ORIGINAL_DOT_SIZE * SCALE_FACTOR)
    if DOT_SIZE < 2: DOT_SIZE = 2

def draw_led_ring(screen, active_leds, total_leds, state, breathing_alpha=255):
    ring_center_y = CENTER_Y + OFFSET_RING_Y
    
    for i in range(total_leds):
        angle = math.radians(-90 + (360 / total_leds) * i)
        # WICHTIG: Für gfxdraw brauchen wir die Koordinaten als Integer (ganze Zahlen)
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

        # --- ZEICHNEN (Optimiert für Schärfe) ---
        if is_lit:
            # Fall 1: Transparente/Atmende Kreise (nutzt weiterhin Surface-Methode)
            if breathing_alpha < 255 or state == STATE_CLEARANCE:
                target_surface = pygame.Surface((DOT_SIZE*2, DOT_SIZE*2), pygame.SRCALPHA)
                r, g, b = current_color
                pygame.draw.circle(target_surface, (r, g, b, breathing_alpha), (DOT_SIZE, DOT_SIZE), DOT_SIZE)
                screen.blit(target_surface, (x_int-DOT_SIZE, y_int-DOT_SIZE))
            
            # Fall 2: Solide, scharfe Kreise (nutzt NEU gfxdraw)
            else:
                # 1. Den gefüllten Kreis zeichnen
                gfxdraw.filled_circle(screen, x_int, y_int, DOT_SIZE, current_color)
                # 2. Einen perfekt geglätteten (anti-aliased) Ring darüber legen für scharfe Kanten
                gfxdraw.aacircle(screen, x_int, y_int, DOT_SIZE, current_color)

        else:
            # Auch die "ausgeschalteten" grauen Kreise sollen scharf sein
            gfxdraw.filled_circle(screen, x_int, y_int, DOT_SIZE, COLOR_LED_OFF)
            gfxdraw.aacircle(screen, x_int, y_int, DOT_SIZE, COLOR_LED_OFF)

def main():
    pygame.init()
    pygame.display.set_mode((100, 100))
    load_images()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Smart Traffic Light (High Res Dots)")
    clock = pygame.time.Clock()
    
    current_state = STATE_GREEN
    led_counter = TOTAL_LEDS 
    last_tick = pygame.time.get_ticks()
    
    breathing_value = 0
    clearance_start_time = 0
    tram_display_timer = 0
    
    running = True
    while running:
        keys = pygame.key.get_pressed()
        slow_walker_detected = keys[pygame.K_SPACE] 
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_t: 
                    print("Tram erkannt! Resetting...")
                    current_state = STATE_TRAM
                    tram_display_timer = pygame.time.get_ticks()

        now = pygame.time.get_ticks()
        breath_alpha = int(155 + 100 * math.sin(now * 0.005)) 

        if current_state == STATE_TRAM:
            if now - tram_display_timer > 2000:
                current_state = STATE_RED 
                led_counter = 0

        elif current_state == STATE_CLEARANCE:
            if now - clearance_start_time > CLEARANCE_TIME_MS:
                current_state = STATE_RED
                led_counter = 0

        elif now - last_tick >= TICK_INTERVAL:
            if slow_walker_detected and current_state == STATE_GREEN:
                pass 
            else:
                last_tick = now
                if current_state == STATE_GREEN:
                    led_counter -= 1
                    if led_counter < 0:
                        current_state = STATE_CLEARANCE
                        clearance_start_time = now
                        led_counter = 0 
                elif current_state == STATE_RED:
                    led_counter += 1
                    if led_counter > TOTAL_LEDS:
                        current_state = STATE_GREEN
                        led_counter = TOTAL_LEDS 

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
            draw_led_ring(screen, TOTAL_LEDS, TOTAL_LEDS, STATE_TRAM, 255)

        elif current_state == STATE_CLEARANCE:
            flash_alpha = int(128 + 127 * math.sin(now * 0.015)) 
            draw_led_ring(screen, TOTAL_LEDS, TOTAL_LEDS, STATE_CLEARANCE, flash_alpha)

        elif current_state == STATE_GREEN:
            alpha = breath_alpha if slow_walker_detected else 255
            draw_led_ring(screen, led_counter, TOTAL_LEDS, STATE_GREEN, alpha)
            
        else: 
            draw_led_ring(screen, led_counter, TOTAL_LEDS, STATE_RED, 255)

        pygame.display.flip() 
        clock.tick(60) 

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()