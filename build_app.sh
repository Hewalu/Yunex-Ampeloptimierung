#!/bin/bash
# ============================================================
#  TrafficOwl – Build-Skript für macOS Standalone-App
# ============================================================
#  Erstellt eine eigenständige TrafficOwl.app, die ohne Python-
#  Installation auf jedem Mac läuft.
#
#  Voraussetzung: Dieses Skript wird auf dem MacBook Air
#  ausgeführt, wo Python 3.13 + alle Libraries installiert sind.
#
#  Nutzung:   chmod +x build_app.sh && ./build_app.sh
#  Ergebnis:  dist/TrafficOwl.app  (auf USB-Stick kopierbar)
# ============================================================

set -e  # Bei Fehler abbrechen

echo "╔══════════════════════════════════════════════════╗"
echo "║       TrafficOwl – macOS App Builder             ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# --- Zum Projektverzeichnis wechseln ---
cd "$(dirname "$0")"
echo "📂 Projektverzeichnis: $(pwd)"

# --- Prüfen ob Python verfügbar ---
PYTHON=${PYTHON:-python3.13}
if ! command -v "$PYTHON" &> /dev/null; then
    PYTHON=python3
fi
echo "🐍 Python: $($PYTHON --version)"

# --- PyInstaller installieren falls nötig ---
if ! $PYTHON -m PyInstaller --version &> /dev/null 2>&1; then
    echo "📦 Installiere PyInstaller..."
    $PYTHON -m pip install pyinstaller
fi
echo "🔧 PyInstaller: $($PYTHON -m PyInstaller --version 2>/dev/null || echo 'wird installiert')"

# --- Vorherige Builds aufräumen ---
echo ""
echo "🧹 Räume vorherige Builds auf..."
rm -rf build/ dist/TrafficOwl dist/TrafficOwl.app

# --- Build starten ---
echo ""
echo "🔨 Starte Build... (das dauert 2-5 Minuten)"
echo "   Alle Libraries, das YOLO-Modell und die Assets werden gebündelt."
echo ""

$PYTHON -m PyInstaller TrafficOwl.spec --noconfirm

# --- Ergebnis prüfen ---
echo ""
if [ -d "dist/TrafficOwl.app" ]; then
    APP_SIZE=$(du -sh "dist/TrafficOwl.app" | cut -f1)
    echo "✅ Build erfolgreich!"
    echo ""
    echo "   📱 App:    dist/TrafficOwl.app"
    echo "   📏 Größe:  $APP_SIZE"
    echo ""
    echo "╔══════════════════════════════════════════════════╗"
    echo "║  Nächste Schritte:                               ║"
    echo "║                                                  ║"
    echo "║  1. USB-Stick einstecken                         ║"
    echo "║  2. dist/TrafficOwl.app auf den Stick kopieren   ║"
    echo "║  3. Am iMac: Stick einstecken                    ║"
    echo "║  4. TrafficOwl.app doppelklicken                 ║"
    echo "║  5. Bei Gatekeeper-Warnung:                      ║"
    echo "║     Rechtsklick → Öffnen → Öffnen bestätigen     ║"
    echo "║  6. ESP per USB anschließen (wird auto-erkannt)  ║"
    echo "╚══════════════════════════════════════════════════╝"
else
    echo "❌ Build fehlgeschlagen! Siehe Fehlermeldungen oben."
    exit 1
fi
