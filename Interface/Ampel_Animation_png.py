import pygame
import math
import sys
import os

# ==========================================
#      HIER DEINE KONFIGURATION
# ==========================================

# 1. FENSTERGRÖSSE
SCALE_FACTOR = 0.3   

# 2. ANZAHL UND ZEIT
TOTAL_LEDS = 24      
SECONDS_PER_LED = 0.5 

# 3. POSITIONIERUNG
# Positive Zahl (+) = Nach UNTEN, Negative Zahl (-) = Nach OBEN
OFFSET_ROT_Y   = -230  
OFFSET_GRUEN_Y = 230   
OFFSET_RING_Y  = -2    

# 4. LED OPTIK
ORIGINAL_LED_RADIUS = 235  
ORIGINAL_DOT_SIZE   = 25   

# 5. FARBEN
COLOR_LED_ON  = (255, 255, 255)  # Weiß
COLOR_LED_OFF = (60, 60, 60)     # Dunkelgrau

# ==========================================
# AB HIER SYSTEM CODE
# ==========================================

WIDTH, HEIGHT = 0, 0 
CENTER_X, CENTER_Y = 0, 0
LED_RADIUS = 0
DOT_SIZE = 0
TICK_INTERVAL = int(SECONDS_PER_LED * 1000) 
images = {}

def load_and_scale_image(path):
    try:
        img = pygame.image.load(path).convert_alpha()
        new_width = int(img.get_width() * SCALE_FACTOR)
        new_height = int(img.get_height() * SCALE_FACTOR)
        return pygame.transform.smoothscale(img, (new_width, new_height))
    except pygame.error as e:
        print(f"Fehler bei {path}: {e}")
        sys.exit()

def load_images():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    asset_dir = os.path.join(script_dir, "assets")
    
    print(f"Lade Bilder aus: {asset_dir}")

    try:
        images['housing'] = load_and_scale_image(os.path.join(asset_dir, 'gehaeuse.png'))
        images['red_on'] = load_and_scale_image(os.path.join(asset_dir, 'mann_rot_an.png'))
        images['red_off'] = load_and_scale_image(os.path.join(asset_dir, 'mann_rot_aus.png'))
        images['green_on'] = load_and_scale_image(os.path.join(asset_dir, 'mann_gruen_an.png'))
        images['green_off'] = load_and_scale_image(os.path.join(asset_dir, 'mann_gruen_aus.png'))
        
        global WIDTH, HEIGHT, CENTER_X, CENTER_Y, LED_RADIUS, DOT_SIZE
        WIDTH = images['housing'].get_width()
        HEIGHT = images['housing'].get_height()
        CENTER_X = WIDTH // 2
        CENTER_Y = HEIGHT // 2
        
        LED_RADIUS = int(ORIGINAL_LED_RADIUS * SCALE_FACTOR)
        DOT_SIZE = int(ORIGINAL_DOT_SIZE * SCALE_FACTOR)
        
        if DOT_SIZE < 2: DOT_SIZE = 2
        
    except Exception as e:
        print(f"Fehler: {e}")
        sys.exit()

def draw_led_ring(screen, active_leds, total_leds, is_counting_down):
    ring_center_y = CENTER_Y + OFFSET_RING_Y
    
    for i in range(total_leds):
        # Winkel berechnen (Start bei -90 Grad = 12 Uhr)
        angle = math.radians(-90 + (360 / total_leds) * i)
        x = CENTER_X + LED_RADIUS * math.cos(angle)
        y = ring_center_y + LED_RADIUS * math.sin(angle)
        
        is_lit = False
        
        # --- HIER IST DIE GEÄNDERTE LOGIK ---
        if is_counting_down:
            # GRÜNE PHASE (Countdown):
            # Wir wollen, dass die Dunkelheit im Uhrzeigersinn wächst.
            # Das bedeutet: Die LEDs am ANFANG (0, 1, 2...) gehen zuerst aus.
            # Die LEDs bleiben an, wenn ihr Index GRÖSSER ist als die Anzahl der bereits gelöschten.
            leds_gone = total_leds - active_leds
            if i >= leds_gone: 
                is_lit = True
        else:
            # ROTE PHASE (Auffüllen):
            # Hier füllen wir von 0 an aufwärts auf.
            if i < active_leds: 
                is_lit = True     
        
        color = COLOR_LED_ON if is_lit else COLOR_LED_OFF
        pygame.draw.circle(screen, color, (int(x), int(y)), DOT_SIZE)

def main():
    pygame.init()
    pygame.display.set_mode((100, 100)) 
    load_images() 
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Traffic Light Final")
    clock = pygame.time.Clock()
    
    STATE_GREEN = "GREEN"
    STATE_RED = "RED"
    current_state = STATE_GREEN
    
    led_counter = TOTAL_LEDS 
    last_tick = pygame.time.get_ticks()
    
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        now = pygame.time.get_ticks()
        if now - last_tick >= TICK_INTERVAL:
            last_tick = now
            if current_state == STATE_GREEN:
                led_counter -= 1
                if led_counter < 0:
                    current_state = STATE_RED
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

        if current_state == STATE_GREEN:
            rect = images['red_off'].get_rect(center=pos_rot)
            screen.blit(images['red_off'], rect)
            rect = images['green_on'].get_rect(center=pos_gruen)
            screen.blit(images['green_on'], rect)
            
            draw_led_ring(screen, led_counter, TOTAL_LEDS, True)
        else:
            rect = images['red_on'].get_rect(center=pos_rot)
            screen.blit(images['red_on'], rect)
            rect = images['green_off'].get_rect(center=pos_gruen)
            screen.blit(images['green_off'], rect)
            
            draw_led_ring(screen, led_counter, TOTAL_LEDS, False)

        pygame.display.flip() 
        clock.tick(60) 

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()