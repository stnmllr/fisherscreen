@echo off
rem Startet die Deep-Dive-Oberflaeche (app/deepdive_ui) und oeffnet den Browser.
rem Beenden mit Strg+C in diesem Fenster.
rem Laeuft schon eine Instanz auf dem Port, bricht der Start ab; der Browser
rem zeigt dann die laufende Instanz.

cd /d "%~dp0"

rem Browser verzoegert oeffnen (~4 s), damit uvicorn bis dahin lauscht. ping statt
rem timeout: timeout bricht ohne echte Konsole ab ("Eingabeumleitung").
start "" /b cmd /c "ping -n 5 127.0.0.1 >nul & start "" http://127.0.0.1:8765/"

uv run python -m app.deepdive_ui
