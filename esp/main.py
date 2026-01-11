import sys
from machine import Pin
import time

# Pin Konfiguration
# Hauptampel (Fußgänger)
PIN_MAIN_RED = 13
PIN_MAIN_GREEN = 32

# Autoampel (Invertiert/Neben)
PIN_CAR_RED = 12
PIN_CAR_YELLOW = 26
PIN_CAR_GREEN = 33

led_main_red = Pin(PIN_MAIN_RED, Pin.OUT)
led_main_green = Pin(PIN_MAIN_GREEN, Pin.OUT)
led_car_red = Pin(PIN_CAR_RED, Pin.OUT)
led_car_yellow = Pin(PIN_CAR_YELLOW, Pin.OUT)
led_car_green = Pin(PIN_CAR_GREEN, Pin.OUT)

def set_lights(m_red, m_green, c_red, c_yellow, c_green):
    led_main_red.value(m_red)
    led_main_green.value(m_green)
    led_car_red.value(c_red)
    led_car_yellow.value(c_yellow)
    led_car_green.value(c_green)

def main():
    # Initialer Test
    print("ESP32 Ready. Waiting for LED commands...")
    # Format: L <MR> <MG> <CR> <CY> <CG>
    # Beispiel: L 1 0 0 0 1  (Main Rot, Car Grün)
    
    while True:
        try:
            line = sys.stdin.readline()
            if not line: continue
            
            parts = line.strip().split()
            if len(parts) == 0: continue
            
            cmd = parts[0].upper()
            
            if cmd == "L" and len(parts) >= 6:
                # Parse integer values representing 0 or 1
                mr = int(parts[1])
                mg = int(parts[2])
                cr = int(parts[3])
                cy = int(parts[4])
                cg = int(parts[5])
                set_lights(mr, mg, cr, cy, cg)
                
        except Exception as e:
            pass


if __name__ == "__main__":
    main()
