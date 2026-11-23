# Zweistufiger Bau. Die erste Stufe installiert die Abhaengigkeiten, die
# zweite enthaelt nur noch das Ergebnis. Das haelt das Abbild klein und
# reduziert die Angriffsflaeche, weil keine Bauwerkzeuge mitgeliefert werden.

FROM python:3.12-slim AS bau
WORKDIR /install
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install/pakete -r requirements.txt

FROM python:3.12-slim
# Nicht als root laufen. Das ist eine der ersten Fragen jeder Sicherheitspruefung.
RUN useradd --create-home --uid 10001 scout
WORKDIR /app
COPY --from=bau /install/pakete /usr/local
COPY --chown=scout:scout . .
# Zur Laufzeit nicht benoetigte und teils vertrauliche Dateien entfernen
RUN rm -f .env vorqualifiziert.db memory_store.json audit_log.jsonl \
    && rm -rf __pycache__ .git \
    && chown -R scout:scout /app

USER scout
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000
EXPOSE 8000

# Azure Container Apps setzt PORT selbst. Die Shell-Form ist noetig, damit die
# Variable ausgewertet wird.
CMD uvicorn server:app --host 0.0.0.0 --port ${PORT}
