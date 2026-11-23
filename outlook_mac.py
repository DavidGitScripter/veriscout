"""
outlook_mac.py — uebergibt einen Anschreiben-Entwurf an Outlook fuer Mac.

Das Referenzmodell verlangt, dass keine Nachricht ohne menschliche Freigabe
hinausgeht. Diese Bruecke erfuellt das strikt: Sie erzeugt in Outlook einen
OFFENEN ENTWURF mit Empfaenger, BCC, Betreff und Text und legt ihn dem Menschen
zur Pruefung vor. Gesendet wird nichts. Der Versand bleibt ein bewusster Klick
in Outlook.

Technisch laeuft die Uebergabe ueber AppleScript, weil Outlook fuer Mac darueber
skriptbar ist und die Adressen dabei sauber gesetzt werden koennen. Ein
mailto-Link waere unzuverlaessig, weil BCC dort je nach Programm verworfen wird.

Voraussetzungen:
  - macOS mit installiertem Microsoft Outlook
  - Beim ersten Aufruf fragt macOS nach der Erlaubnis, Outlook zu steuern
    (Systemeinstellungen -> Datenschutz & Sicherheit -> Automation)
"""
from __future__ import annotations

import platform
import shutil
import subprocess


class OutlookNichtVerfuegbar(RuntimeError):
    """Outlook kann auf diesem System nicht angesprochen werden."""


def verfuegbar() -> tuple[bool, str]:
    """Prueft, ob eine Uebergabe an Outlook grundsaetzlich moeglich ist."""
    if platform.system() != "Darwin":
        return False, "Kein macOS — Outlook-Uebergabe nur auf dem Mac verfuegbar."
    if not shutil.which("osascript"):
        return False, "osascript nicht gefunden."
    try:
        r = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to '
             '(name of processes) contains "Microsoft Outlook"'],
            capture_output=True, text=True, timeout=8)
        # Auch wenn Outlook gerade nicht laeuft, ist die Uebergabe moeglich —
        # AppleScript startet das Programm bei Bedarf. Der Aufruf oben dient nur
        # dazu, fehlende Automatisierungsrechte frueh zu erkennen.
        if r.returncode != 0 and "not allowed" in (r.stderr or "").lower():
            return False, ("Automatisierungsrechte fehlen. In den "
                           "Systemeinstellungen unter Datenschutz & Sicherheit "
                           "-> Automation den Zugriff auf Outlook erlauben.")
    except Exception as e:
        return False, f"Pruefung fehlgeschlagen: {e}"
    return True, "Outlook-Uebergabe verfuegbar."


def _escape(text: str) -> str:
    """Maskiert Zeichen, die AppleScript-Zeichenketten sonst zerlegen wuerden."""
    return (text or "").replace("\\", "\\\\").replace('"', '\\"')


HINWEIS_OHNE_EMPFAENGER = (
    ">>> Empfaenger bitte selbst eintragen. Fuer dieses Startup liess sich "
    "keine belegte Kontaktadresse ermitteln. Diese Zeile vor dem Versand "
    "loeschen. <<<\n\n")


def entwurf_erstellen(to: str, subject: str, body: str,
                      bcc: str = "", oeffnen: bool = False) -> dict:
    """Legt in Outlook einen Entwurf an. Es wird ausdruecklich NICHT gesendet.

    Standardmaessig entsteht der Entwurf still im Ordner Entwuerfe. Nur wenn
    ``oeffnen`` gesetzt ist, kommt Outlook in den Vordergrund. Bei mehreren
    Freigaben hintereinander wuerden sonst ebenso viele Fenster aufspringen.

    Fehlt die Empfaengeradresse, entsteht der Entwurf trotzdem, allerdings mit
    leerem Empfaengerfeld und einem Hinweis im Text. Eine geratene Adresse
    einzutragen waere gefaehrlicher als ein leeres Feld, weil sie beim
    fluechtigen Lesen wie eine gepruefte Angabe aussieht.
    """
    ok, grund = verfuegbar()
    if not ok:
        raise OutlookNichtVerfuegbar(grund)

    to = (to or "").strip()
    ohne_empfaenger = not to
    if ohne_empfaenger:
        body = HINWEIS_OHNE_EMPFAENGER + (body or "")

    zeilen = [
        'tell application "Microsoft Outlook"',
        '  set neuerEntwurf to make new outgoing message with properties '
        f'{{subject:"{_escape(subject)}", content:"{_escape(body)}"}}',
        '  tell neuerEntwurf',
    ]
    if to:
        zeilen.append(
            '    make new recipient with properties {email address:{address:"'
            f'{_escape(to)}"}}}}')
    if bcc:
        zeilen.append(
            '    make new bcc recipient with properties {email address:{address:"'
            f'{_escape(bcc)}"}}}}')
    zeilen.append('  end tell')
    if oeffnen:
        zeilen.append('  open neuerEntwurf')
        zeilen.append('  activate')
    zeilen.append('  return id of neuerEntwurf')
    zeilen.append('end tell')
    script = "\n".join(zeilen)

    r = subprocess.run(["osascript", "-e", script],
                       capture_output=True, text=True, timeout=25)
    if r.returncode != 0:
        raise OutlookNichtVerfuegbar(
            f"Outlook meldete einen Fehler: {(r.stderr or '').strip()[:200]}")
    return {
        "status": "entwurf_in_outlook",
        "outlook_id": (r.stdout or "").strip(),
        "to": to,
        "bcc": bcc,
        "subject": subject,
        "geoeffnet": bool(oeffnen),
        "ohne_empfaenger": ohne_empfaenger,
        "gesendet": False,
        "hinweis": ("Entwurf liegt in Outlook, Empfaenger ist leer und muss "
                    "ergaenzt werden." if ohne_empfaenger else
                    "Entwurf liegt in Outlook. Der Versand bleibt bei Ihnen."),
    }
