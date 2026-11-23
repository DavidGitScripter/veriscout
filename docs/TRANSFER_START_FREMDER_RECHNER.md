# VeriScout auf dem eigenen Rechner starten (kostenloser Transfermodus)

Für die bewertenden Personen, Teil 2. Es entstehen keine Kosten, es wird kein API-Schlüssel gebraucht, und es wird nichts an ein CRM oder E-Mail-System gesendet.

Voraussetzung: Python 3.12 oder neuer. Prüfen mit `python3 --version` (Windows: `py --version`).

## 1. Paket entpacken

Die ZIP-Datei von David entpacken. Es entsteht ein Ordner `veriscout`. Im Terminal in diesen Ordner wechseln.

## 2. Einmalig einrichten (etwa 1 bis 3 Minuten, je nach Internet)

macOS und Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install fastapi==0.141.1 uvicorn==0.52.1
```

Windows (PowerShell):

```powershell
py -3 -m venv .venv
.venv\Scripts\python -m pip install fastapi==0.141.1 uvicorn==0.52.1
```

Für den Transfermodus genügen diese zwei Pakete. Die übrigen Pakete aus `requirements.txt` braucht nur der kostenpflichtige Live-Betrieb.

## 3. Starten

macOS und Linux:

```bash
.venv/bin/python scripts/start_transfer_review.py
```

Windows:

```powershell
.venv\Scripts\python scripts\start_transfer_review.py
```

Dann im Browser `http://127.0.0.1:8001` öffnen und den Bereich „Transferprüfung“ wählen. Beenden mit Strg+C im Terminal.

## Wenn etwas nicht klappt

- „python3: command not found“ (macOS): Python von python.org installieren. Das ist der unsicherste Schritt und kann 5 bis 10 Minuten dauern.
- „Address already in use“: `--port 8002` anhängen und `http://127.0.0.1:8002` öffnen.
- Jede Hilfe von David per Nachricht wird mit Uhrzeit protokolliert.

Geprüft am 06.11.2026 in einer frischen Linux-Umgebung mit Python 3.13: Entpacken, Einrichten und Start dauerten zusammen etwa 30 Sekunden bei schnellem Netz, die Startseite antwortete mit Status 200. Auf macOS und Windows ist der Ablauf nicht getestet; der Windows-Start ist insofern ungeprüft.
