# TrafficOwl – Standalone macOS App bauen

## Übersicht

Die App wird auf deinem **MacBook Air** gebaut (wo Python + Libraries installiert sind) und dann als fertige `.app` auf den **iMac** kopiert. Auf dem iMac braucht man **kein Python, kein VS Code, keine Libraries**.

## Was wird gebündelt?

| Komponente | Beschreibung |
|---|---|
| Python 3.13 Runtime | Komplette Python-Umgebung |
| PyTorch + YOLO | Für die Personenerkennung |
| OpenCV | Kamera + Bildverarbeitung |
| Pygame | UI-Rendering |
| PySerial | ESP32-Kommunikation |
| `yolo26n-seg.pt` | YOLO-Modell (~6 MB) |
| `Interface/assets/*.png` | Alle Ampel-Grafiken |
| `esp_control.py` | ESP-Steuerung |
| `traffic_logic.py` | Ampellogik |

## Build-Anleitung (auf dem MacBook Air)

### 1. PyInstaller installieren (einmalig)

```bash
pip install pyinstaller
```

### 2. App bauen

```bash
cd "/Users/tobi/Library/Mobile Documents/com~apple~CloudDocs/@Fluss/@CE/3. Sem/Module/Systems/03_Projects/TrafficOul_Code/Code/Yunex-Ampeloptimierung"

chmod +x build_app.sh
./build_app.sh
```

Das dauert ca. **2-5 Minuten**. Ergebnis: `dist/TrafficOwl.app`

### 3. Auf USB-Stick kopieren

Die gesamte `TrafficOwl.app` aus `dist/` auf den USB-Stick ziehen.

> **Größe:** Die App wird ca. 500 MB - 1.5 GB groß (PyTorch + YOLO + OpenCV sind große Libraries).

## Auf dem iMac starten

### 1. App vom USB-Stick starten

- USB-Stick einstecken
- `TrafficOwl.app` doppelklicken
- Oder: App vom Stick auf den Desktop / Applications kopieren, dann starten

### 2. Gatekeeper-Warnung umgehen

Da die App nicht aus dem App Store kommt, zeigt macOS eine Warnung:

> **"TrafficOwl" kann nicht geöffnet werden, da der Entwickler nicht verifiziert werden kann.**

**Lösung:**
1. **Rechtsklick** auf `TrafficOwl.app`
2. **„Öffnen"** im Kontextmenü wählen
3. Im Dialog auf **„Öffnen"** klicken

Das muss nur beim **ersten Mal** gemacht werden.

**Alternativ** (falls das nicht klappt):
```bash
# Im Terminal auf dem iMac:
xattr -cr /Pfad/zu/TrafficOwl.app
```

### 3. ESP anschließen

- ESP32 per USB an den iMac anschließen
- Die App erkennt den ESP **automatisch** (sucht nach USB-Serial-Ports)
- Wenn der ESP nicht erkannt wird: ggf. den [CH340/CP2102 Treiber](https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers) auf dem iMac installieren

### 4. Kamera-Zugriff

Beim ersten Start fragt macOS nach Kamera-Berechtigung. **Erlauben** klicken.

## Tastenkürzel

| Taste | Funktion |
|---|---|
| **F** | Vollbild an/aus |
| **G** | Ampelzyklus starten |
| **T** | Tram-Modus |
| **Space** | Slow-Modus |
| **ESC** | Beenden |

## Troubleshooting

### App startet nicht / Schwarzer Bildschirm / Kein Kamerabild
- Die App öffnet automatisch ein Terminal-Fenster mit Debug-Logs
- Dort stehen alle Fehlermeldungen (z.B. "Modell nicht gefunden", "Kamera konnte nicht geöffnet werden", etc.)
- Alternativ: Rechtsklick → „Paketinhalt zeigen" → `Contents/MacOS/TrafficOwl` im Terminal starten
- Wenn alles funktioniert und du das Terminal-Fenster loswerden willst: In `TrafficOwl.spec` die Zeile `console=True` auf `console=False` ändern und neu bauen

### Kamera funktioniert nicht
- Systemeinstellungen → Datenschutz & Sicherheit → Kamera → TrafficOwl erlauben

### ESP wird nicht erkannt
- USB-Kabel prüfen (muss Datenkabel sein, kein reines Ladekabel)
- ggf. CH340/CP2102 Treiber installieren

### App ist zu groß
- Die Größe kommt hauptsächlich von PyTorch (~400 MB). Das ist normal für ML-Apps.

## Wichtig: Architektur

- **MacBook Air M1/M2/M3** → baut eine **arm64** App
- Die gebaute App läuft nur auf Macs mit der **gleichen Architektur**
- Wenn der iMac ein **Intel**-Mac ist und dein MacBook ein **M-Chip** hat, muss der Build auf einem Intel-Mac oder mit Rosetta gemacht werden

Falls der iMac Intel hat:
```bash
# Auf dem M-Chip MacBook mit Rosetta bauen:
arch -x86_64 ./build_app.sh
```
