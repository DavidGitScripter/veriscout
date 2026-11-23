"""Verifizierte TLS-Kontexte, auch bei macOS-Python ohne eigenes CA-Bundle."""
import os
import ssl
import sys
from pathlib import Path


def verified_tls_context():
    context = ssl.create_default_context()
    # Explizite Nutzerkonfiguration hat Vorrang. Niemals CERT_NONE verwenden.
    if (sys.platform == "darwin" and not os.environ.get("SSL_CERT_FILE")
            and context.cert_store_stats().get("x509_ca", 0) == 0
            and Path("/etc/ssl/cert.pem").is_file()):
        context.load_verify_locations(cafile="/etc/ssl/cert.pem")
    return context


def source_tls_context():
    """TLS-Kontext fuer den Quellenabruf (12.11.2026).

    Nutzt ueber ``truststore`` die Zertifikatspruefung des Betriebssystems. Diese
    ergaenzt fehlende Zwischenzertifikate (unvollstaendige Serverkette), prueft
    aber genauso streng (Hostname, Kette, Gueltigkeit). Ohne das Paket gilt der
    bisherige Kontext. Die Modell-APIs nutzen weiter ``verified_tls_context``.
    """
    try:
        import truststore
    except ImportError:  # pragma: no cover - Paket fehlt
        return verified_tls_context()
    context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context
