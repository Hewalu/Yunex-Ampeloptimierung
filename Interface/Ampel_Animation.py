import pygame
import math
import sys

# --- Konfiguration ---
# Fenstergröße
WIDTH, HEIGHT = 300, 900
CENTER_X = WIDTH // 2

# Farben (R, G, B)
COLOR_BG = (30, 30, 30)         # Dunkles Grau für das Gehäuse
COLOR_BLACK = (0, 0, 0)         # Schwarz für die Kreise
COLOR_OFF = (50, 50, 50)        # Farbe für "ausgeschaltete" Lampen
COLOR_RED = (255, 0, 0)         # Rotes Licht
COLOR_GREEN = (0, 255, 0)       # Grünes Licht
COLOR_LED_ON = (255, 255, 255)  # Weiße LEDs
COLOR_LED_OFF = (60, 60, 60)    # Dunkle LEDs

# LED Konfiguration
TOTAL_LEDS = 30                 # Anzahl der Punkte im Kreis
LED_RADIUS = 120                # Radius des Kreises der Punkte
DOT_SIZE = 8                    # Größe eines einzelnen Punktes

# Zeitsteuerung
TICK_INTERVAL = 1000            # 1000 Millisekunden = 1 Sekunde

def init_pygame():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Ampel Animation")
    return screen

def draw_housing(screen):
    """Zeichnet den Kasten der Ampel"""
    # Drei Abschnitte
    rect_height = HEIGHT // 3
    
    # Oberer Kasten (Rot)
    pygame.draw.rect(screen, COLOR_BG, (0, 0, WIDTH, rect_height))
    pygame.draw.circle(screen, COLOR_BLACK, (CENTER_X, rect_height // 2), 130)
    
    # Mittlerer Kasten (Timer)
    pygame.draw.rect(screen, COLOR_BG, (0, rect_height, WIDTH, rect_height))
    pygame.draw.circle(screen, COLOR_BLACK, (CENTER_X, rect_height + rect_height // 2), 130)

    # Unterer Kasten (Grün)
    pygame.draw.rect(screen, COLOR_BG, (0, 2 * rect_height, WIDTH, rect_height))
    pygame.draw.circle(screen, COLOR_BLACK, (CENTER_X, 2 * rect_height + rect_height // 2), 130)
    
    # Trennlinien
    pygame.draw.line(screen, (0,0,0), (0, rect_height), (WIDTH, rect_height), 5)
    pygame.draw.line(screen, (0,0,0), (0, 2*rect_height), (WIDTH, 2*rect_height), 5)

def draw_red_man(screen, is_on):
    """Zeichnet das stehende Männchen (Rot)"""
    color = COLOR_RED if is_on else COLOR_OFF
    center_y = HEIGHT // 6
    
    # Kopf
    pygame.draw.circle(screen, color, (CENTER_X, center_y - 50), 20)
    # Körper (Rechteck)
    pygame.draw.rect(screen, color, (CENTER_X - 15, center_y - 25, 30, 60))
    # Arme (Linien)
    pygame.draw.line(screen, color, (CENTER_X - 15, center_y - 20), (CENTER_X - 15, center_y + 20), 10) # Links
    pygame.draw.line(screen, color, (CENTER_X + 15, center_y - 20), (CENTER_X + 15, center_y + 20), 10) # Rechts
    # Beine
    pygame.draw.line(screen, color, (CENTER_X - 10, center_y + 35), (CENTER_X - 10, center_y + 80), 10)
    pygame.draw.line(screen, color, (CENTER_X + 10, center_y + 35), (CENTER_X + 10, center_y + 80), 10)

def draw_green_man(screen, is_on):
    """Zeichnet das gehende Männchen (Grün)"""
    color = COLOR_GREEN if is_on else COLOR_OFF
    center_y = (HEIGHT // 6) * 5
    
    # Kopf
    pygame.draw.circle(screen, color, (CENTER_X, center_y - 50), 20)
    # Körper
    pygame.draw.rect(screen, color, (CENTER_X - 15, center_y - 25, 30, 50))
    # Arme (Schwingend)
    pygame.draw.line(screen, color, (CENTER_X - 15, center_y - 20), (CENTER_X - 35, center_y + 10), 10) # Hinten
    pygame.draw.line(screen, color, (CENTER_X + 15, center_y - 20), (CENTER_X + 35, center_y + 10), 10) # Vorne
    # Beine (Schritt)
    pygame.draw.line(screen, color, (CENTER_X - 10, center_y + 25), (CENTER_X - 30, center_y + 70), 10) # Hinten
    pygame.draw.line(screen, color, (CENTER_X + 10, center_y + 25), (CENTER_X + 30, center_y + 70), 10) # Vorne

def draw_led_ring(screen, active_leds, total_leds, is_counting_down):
    """Zeichnet den Ring aus Punkten im mittleren Feld"""
    center_y = HEIGHT // 2
    
    for i in range(total_leds):
        # Winkel berechnen (Start bei -90 Grad also 12 Uhr)
        angle = math.radians(-90 + (360 / total_leds) * i)
        
        x = CENTER_X + LED_RADIUS * math.cos(angle)
        y = center_y + LED_RADIUS * math.sin(angle)
        
        # Logik: Welche LEDs sind an?
        # Wenn Countdown (Grün): LEDs verschwinden
        # Wenn Auffüllen (Rot): LEDs erscheinen
        is_lit = False
        if is_counting_down:
            if i < active_leds:
                is_lit = True
        else:
            if i < active_leds:
                is_lit = True
                
        color = COLOR_LED_ON if is_lit else COLOR_LED_OFF
        pygame.draw.circle(screen, color, (int(x), int(y)), DOT_SIZE)

def main():
    screen = init_pygame()
    clock = pygame.time.Clock()
    
    # Zustandsvariablen
    STATE_GREEN = "GREEN" # Ampel ist Grün, Punkte zählen runter
    STATE_RED = "RED"     # Ampel ist Rot, Punkte zählen hoch
    
    current_state = STATE_GREEN
    
    # Timer Setup
    led_counter = TOTAL_LEDS # Startet voll bei Grün
    last_tick = pygame.time.get_ticks()
    
    running = True
    while running:
        # 1. Event Handling (Fenster schließen)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        # 2. Logik & Zeitmessung
        now = pygame.time.get_ticks()
        if now - last_tick >= TICK_INTERVAL:
            last_tick = now
            
            if current_state == STATE_GREEN:
                # Runterzählen (ein Punkt verschwindet)
                led_counter -= 1
                if led_counter < 0:
                    # Wechsel zu Rot
                    current_state = STATE_RED
                    led_counter = 0 # Startet leer bei Rot
            
            elif current_state == STATE_RED:
                # Hochzählen (Punkte füllen sich auf)
                led_counter += 1
                if led_counter > TOTAL_LEDS:
                    # Wechsel zu Grün
                    current_state = STATE_GREEN
                    led_counter = TOTAL_LEDS # Startet voll bei Grün

        # 3. Zeichnen
        screen.fill((0, 0, 0)) # Hintergrund säubern
        draw_housing(screen)
        
        if current_state == STATE_GREEN:
            draw_red_man(screen, is_on=False)
            draw_green_man(screen, is_on=True)
            draw_led_ring(screen, led_counter, TOTAL_LEDS, is_counting_down=True)
            
        else: # STATE_RED
            draw_red_man(screen, is_on=True)
            draw_green_man(screen, is_on=False)
            draw_led_ring(screen, led_counter, TOTAL_LEDS, is_counting_down=False)

        pygame.display.flip() # Bild aktualisieren
        clock.tick(60) # Begrenzung auf 60 FPS

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()