from machine import Pin
import time

# --- KONFIGURATION ---
# Hall-Sensor an GPIO 4 (oft D2)
hall_sensor = Pin(13, Pin.IN, Pin.PULL_UP)

# Onboard LED ist meistens an GPIO 2 (oft D4)
led = Pin(2, Pin.OUT)

# Sicherstellen, dass die LED am Start AUS ist.
# Bei den meisten ESPs ist 1 = AUS. Falls sie leuchtet, ändere es auf 0.
led.value(1) 

print("System bereit. Warte auf Magnet...")

while True:
    # Sensor zieht auf 0 (LOW), wenn Magnet da ist
    if hall_sensor.value() == 0:
        print("Magnet erkannt! LED an.")
        
        # LED einschalten (bei ESP8266 oft 0, bei reinem ESP32 oft 1)
        led.value(1) 
        
        # 2 Sekunden warten
        time.sleep(2)
        
        # LED wieder ausschalten
        led.value(0)
        
        print("LED wieder aus. Warte neu...")
        
    # Kurze Pause für den Prozessor
    time.sleep(0.1)