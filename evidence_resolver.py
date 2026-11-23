"""Modellunabhaengige Aufloesung und Pruefung nativer Webquellen.

Der Resolver ist in SAS und MAS identisch. Er akzeptiert nur URLs, die zuvor
aus strukturierten Web-Tool-Metadaten stammen, ruft das Dokument direkt ab und
prueft, ob der behauptete Belegauszug im Dokument vorkommt. Fehler werden als
unbekannt behandelt; sie erzeugen nie positive Evidenz.
"""
from __future__ import annotations

import datetime
import difflib
import hashlib
import html
import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
import time
from core import Config
from http_security import source_tls_context, verified_tls_context  # noqa: F401


MAX_DOCUMENT_BYTES = 8_000_000  # PDF-Berichte sind oft groesser als 2 MB
MAX_PDF_PAGES = 60
# Unterseiten derselben Website, die bei fehlendem Auszug zusaetzlich geprueft
# werden (je Auszug hoechstens so viele; Abrufe zaehlen gegen das Resolverbudget).
SUBPAGE_LIMIT = 3
SUBPAGE_KEYWORDS = (
    "ueber", "uber", "about", "unternehmen", "company", "team", "produkt",
    "product", "technolog", "loesung", "losung", "solution", "verfahren",
    "process", "leistung", "service", "impressum", "imprint", "faq", "presse",
    "press", "news", "referenz", "nachhaltig", "sustainab", "recycling",
)
_SKIP_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".css",
                  ".js", ".zip", ".mp4", ".ico", ".woff", ".woff2")


def _same_site_links(html_text: str, base_url: str, limit: int = 60) -> list[str]:
    """Links derselben Website aus einer HTML-Seite (ohne Anker und Dateien)."""
    base_host = (urllib.parse.urlsplit(base_url).hostname or "").lower()
    base_host = base_host[4:] if base_host.startswith("www.") else base_host
    links, seen = [], set()
    for href in re.findall(r"""href\s*=\s*["']([^"']+)["']""", html_text, flags=re.I):
        href = href.split("#", 1)[0].strip()
        if not href:
            continue
        absolute = urllib.parse.urljoin(base_url, html.unescape(href))
        parts = urllib.parse.urlsplit(absolute)
        host = (parts.hostname or "").lower()
        host = host[4:] if host.startswith("www.") else host
        path = parts.path.lower()
        if (parts.scheme not in {"http", "https"} or host != base_host
                or path.endswith(_SKIP_SUFFIXES)
                or any(marker in path for marker in (
                    "/feed", "wp-json", "xmlrpc", "wp-content", "wp-includes",
                    "/tag/", "/author/", "login", "/cart", "/warenkorb"))):
            continue
        clean = urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path or "/",
                                         parts.query, ""))
        if clean.rstrip("/") == base_url.split("#")[0].rstrip("/") or clean in seen:
            continue
        seen.add(clean)
        links.append(clean)
        if len(links) >= limit:
            break
    return links
DEFAULT_TIMEOUT = 15


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Folgt Weiterleitungen nur zu oeffentlichen HTTP(S)-Zielen.

    Jedes Ziel wird erneut auf oeffentliche Erreichbarkeit geprueft; private,
    lokale oder nicht-HTTP-Ziele werden fail-closed blockiert. Die finale
    Adresse wird als resolved_url protokolliert. (Bis 13.10.2026 wurden alle
    Weiterleitungen blockiert; das liess viele echte Quellen als technischen
    Fehler enden, etwa /de/start/ -> /de/start.)
    """
    max_redirections = 5

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urlsplit(newurl)
        if (target.scheme not in {"http", "https"}
                or not _public_host(target.hostname or "")):
            raise urllib.error.HTTPError(
                req.full_url, code, "redirect_blocked_non_public_target",
                headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _public_host(host: str) -> bool:
    host = (host or "").strip().lower().rstrip(".")
    if not host or host in {"localhost", "localhost.localdomain"}:
        return False
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        return False
    for info in infos:
        try:
            address = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (address.is_private or address.is_loopback or address.is_link_local
                or address.is_multicast or address.is_reserved
                or address.is_unspecified):
            return False
    return True


def _pdf_text(raw: bytes) -> str:
    """Text eines PDF (hoechstens MAX_PDF_PAGES Seiten); leer bei Fehlern.

    Ohne lesbaren Text wird kein vermeintlich gepruefter Auszug behauptet.
    """
    try:
        import io
        import logging
        logging.getLogger("pypdf").setLevel(logging.ERROR)
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        parts = []
        for page in reader.pages[:MAX_PDF_PAGES]:
            parts.append(page.extract_text() or "")
        return " ".join(" ".join(parts).split())
    except Exception:
        return ""


def _plain_text(raw: bytes, content_type: str) -> str:
    if "pdf" in (content_type or "").lower() or raw[:5] == b"%PDF-":
        return _pdf_text(raw)
    text = raw.decode("utf-8", errors="replace")
    text = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    return " ".join(text.split())


# M3 (12.11.2026): nur Schreibvarianten angleichen, nie Inhalt. Weiche Trennstriche
# und unsichtbare Zeichen entfallen, Silbentrennung am Zeilenende wird
# zusammengezogen, Ligaturen und Sonderformen per NFKC vereinheitlicht.
# Leerzeichen, Zeilenumbrueche, Anfuehrungszeichen und Bindestrichvarianten
# gleicht die bestehende Regel (alles ausser Buchstaben/Ziffern -> Leerzeichen) an.
_INVISIBLE = re.compile("[\u00ad\u200b\u200c\u200d\u2060\ufeff]")
_LINE_HYPHEN = re.compile(r"(\w)[-\u2010\u2011]\s*\n\s*(\w)")


def _normalise_claim(text: str) -> str:
    import unicodedata
    text = unicodedata.normalize("NFKC", html.unescape(str(text or "")))
    text = _INVISIBLE.sub("", text)
    text = _LINE_HYPHEN.sub(r"\1\2", text)
    text = text.casefold()
    text = re.sub(r"[^a-z0-9äöüß]+", " ", text)
    return " ".join(text.split())


def excerpt_match(excerpt: str, text: str) -> str:
    """Prueft einen normalisierten Auszug gegen normalisierten Dokumenttext.

    Rueckgabe ``exact``, ``fuzzy`` oder ``""``. Der unscharfe Modus verlangt
    mindestens ``EXCERPT_FUZZY_MIN_WORDS`` Woerter und einen Anteil von
    ``EXCERPT_FUZZY_MIN_RATIO`` der Auszugswoerter, die in derselben
    Reihenfolge in einem gleich grossen Dokumentfenster vorkommen. Gleiche
    Stichwoerter in anderer Reihenfolge reichen damit nicht.
    """
    if len(excerpt) < 20 or not text:
        return ""
    if excerpt in text:
        return "exact"
    if Config.EXCERPT_MATCH_MODE != "fuzzy":
        return ""
    return _fuzzy_match(excerpt, text)


def excerpt_match_raw(excerpt: str, text: str) -> str:
    """Wie excerpt_match, beruecksichtigt aber Auslassungszeichen im Rohauszug.

    Ein Auszug der Form "A ... B" gilt im unscharfen Modus nur, wenn jedes
    Teilstueck (mindestens drei, zusammen mindestens sechs Woerter) im
    Dokument gefunden wird.
    """
    import re as _re
    normalised_text = _normalise_claim(text)
    whole = excerpt_match(_normalise_claim(excerpt), normalised_text)
    if whole or Config.EXCERPT_MATCH_MODE != "fuzzy":
        return whole
    parts = [_normalise_claim(part) for part in _re.split(r"\.\.\.|…|\[\.\.\.\]", str(excerpt or ""))]
    parts = [part for part in parts if part]
    if (len(parts) < 2 or any(len(part.split()) < 3 for part in parts)
            or sum(len(part.split()) for part in parts) < 6):
        return ""
    return "segments" if all(
        part in normalised_text or _fuzzy_match(part, normalised_text, min_words=3)
        for part in parts) else ""


def _fuzzy_match(excerpt: str, text: str, min_words: int | None = None) -> str:
    words = excerpt.split()
    if len(words) < (Config.EXCERPT_FUZZY_MIN_WORDS if min_words is None else min_words):
        return ""
    doc = text.split()
    anchors = {word for word in words[:4] if len(word) >= 3}
    slack = max(2, len(words) // 5)
    checked = 0
    for index, word in enumerate(doc):
        if word not in anchors:
            continue
        checked += 1
        if checked > 400:
            break
        start = max(0, index - slack)
        window = doc[start:index + len(words) + slack]
        matcher = difflib.SequenceMatcher(None, words, window, autojunk=False)
        matched = sum(block.size for block in matcher.get_matching_blocks())
        if matched / len(words) >= Config.EXCERPT_FUZZY_MIN_RATIO:
            return "fuzzy"
    return ""


CONTEXT_CHARS = 600


def matched_context(excerpt: str, text: str) -> str:
    """Ausschnitt des normalisierten Dokumenttexts um die Fundstelle.

    Nur zur Dokumentation; die Entscheidung trifft excerpt_match(_raw).
    """
    excerpt = _normalise_claim(excerpt)
    text = _normalise_claim(text)
    if not excerpt or not text:
        return ""
    position = text.find(excerpt)
    if position < 0:
        # Unscharfer Treffer: Fenster mit der groessten Uebereinstimmung.
        words = excerpt.split()
        doc = text.split()
        anchors = {word for word in words[:4] if len(word) >= 3}
        best, best_index, checked = 0.0, -1, 0
        for index, word in enumerate(doc):
            if word not in anchors:
                continue
            checked += 1
            if checked > 400:
                break
            window = doc[index:index + len(words) + 4]
            ratio = difflib.SequenceMatcher(None, words, window, autojunk=False).ratio()
            if ratio > best:
                best, best_index = ratio, index
        if best_index < 0:
            return ""
        position = len(" ".join(doc[:best_index])) + (1 if best_index else 0)
    margin = max(0, (CONTEXT_CHARS - len(excerpt)) // 2)
    start = max(0, position - margin)
    return text[start:start + CONTEXT_CHARS]


def _canonical_domain(url: str) -> str:
    try:
        host = (urllib.parse.urlsplit(str(url or "")).hostname or "").lower().rstrip(".")
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _normalise_family(value: str) -> str:
    value = _normalise_claim(value)
    return value.replace(" ", "-")


# R2 (11.11.2026): Impressum als Existenz- und Sitzbeleg.
IMPRESSUM_PATHS = ("/impressum", "/imprint", "/de/impressum", "/legal-notice", "/en/imprint")
# 12.11.2026: deutsche Registerangaben auch mit englischer Gerichtsbezeichnung
# (z. B. "Register court: Bochum Local Court Register number: HRB 19154"); die
# Nummer muss immer im Seitentext stehen. Oesterreich nur mit FN-Nummer (das
# blosse Wort "Firmenbuch" zaehlt nicht mehr).
_DE_COURT = (r"(Amtsgericht|Registergericht|Handelsregister|Register\s+court|Registration\s+court|"
             r"Local\s+court|District\s+court|Commercial\s+register)")
_REGISTER_PATTERNS = (
    ("DE", re.compile(r"\b(HRB|HRA|GnR|PR|VR)\s*[-:.]?\s*\d{2,7}\s*[A-Z]?\b.{0,80}?" + _DE_COURT + "|"
                      + _DE_COURT + r"\b.{0,80}?\b(HRB|HRA|GnR|PR|VR)\s*[-:.]?\s*\d{2,7}", re.S | re.I)),
    ("AT", re.compile(r"\b(FN|Firmenbuchnummer)\s*[:.]?\s*(FN\s*)?\d{3,7}\s*[a-z]\b", re.I)),
    ("CH", re.compile(r"\bCHE[-‐ ]?\d{3}[.‐ ]?\d{3}[.‐ ]?\d{3}\b")),
)
_VAT_DACH = re.compile(r"\b(DE\s?\d{9}|ATU\s?\d{8}|CHE[-‐ ]?\d{3}[.‐ ]?\d{3}[.‐ ]?\d{3}\s*(MWST|TVA|IVA))\b")
_COUNTRY_WORDS = (("DE", re.compile(r"\b(Deutschland|Germany)\b", re.I)),
                  ("AT", re.compile(r"\b(Österreich|Oesterreich|Austria)\b", re.I)),
                  ("CH", re.compile(r"\b(Schweiz|Switzerland|Suisse|Svizzera)\b", re.I)))
_FOREIGN_WORDS = re.compile(r"\b(United Kingdom|England|USA|United States|Australia|Finland|Czech Republic|"
                            r"Belgium|Netherlands|Nederland|France|Italia|Italy|Spain|España|Sweden|Denmark|"
                            r"Poland|Polska|Norway|Ireland)\b", re.I)


def _name_core(name: str) -> str:
    core = re.sub(r"\b(gmbh|ag|ug|se|kg|co|mbh|haftungsbeschränkt|inc|ltd|s\.r\.o\.)\b\.?", " ",
                  str(name or "").casefold())
    return re.sub(r"[^0-9a-zäöüß]+", " ", core).strip()


def parse_impressum(text: str, company_name: str) -> dict:
    """Prueft deterministisch Firmenname, Registermerkmal und Sitzland."""
    plain = " ".join(str(text or "").split())
    core = _name_core(company_name)
    name_found = bool(core) and core in _name_core(plain)
    register = ""
    register_country = ""
    for country, pattern in _REGISTER_PATTERNS:
        match = pattern.search(plain)
        if match:
            register, register_country = match.group(0)[:120], country
            break
    vat = _VAT_DACH.search(plain)
    if not register and vat:
        register = vat.group(0)
        register_country = ("AT" if register.startswith("ATU") else
                            "CH" if register.startswith("CHE") else "DE")
    word_countries = {code for code, pattern in _COUNTRY_WORDS if pattern.search(plain)}
    foreign = bool(_FOREIGN_WORDS.search(plain)) and not word_countries and not register_country
    country = register_country or (sorted(word_countries)[0] if len(word_countries) == 1 else "")
    if foreign:
        country = "outside_dach"
    excerpt = ""
    if register:
        at = plain.find(register[:20])
        excerpt = plain[max(0, at - 160):at + 160]
    return {"company_name_found": name_found, "register": register,
            "country": country, "excerpt": excerpt}


RETRY_PAUSE_SECONDS = 2.0
RELOCATION_EXTRA_FETCHES = 2


def _replacement_urls(url: str) -> list[str]:
    """Startseite und Sprachvariante (/de <-> /en) des zitierten Pfads."""
    parts = urllib.parse.urlsplit(str(url or ""))
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return []
    base = f"{parts.scheme}://{parts.netloc}"
    path = parts.path or "/"
    out = [base + "/"]
    if path.startswith("/de/") or path == "/de":
        out.append(base + "/en" + path[3:])
    elif path.startswith("/en/") or path == "/en":
        out.append(base + "/de" + path[3:])
    elif path not in {"", "/"}:
        out.append(base + "/de" + path)
    return [u for u in out if u != url]


def _retryable(error) -> bool:
    """Genau ein Wiederholversuch bei Timeout, Verbindungsfehler oder HTTP 429.

    Keine Wiederholung bei 401/403/404 und anderen HTTP-Antworten, und nicht bei
    Zertifikatsfehlern: Sperren und fehlende Seiten werden respektiert.
    """
    import ssl
    if isinstance(error, urllib.error.HTTPError):
        return int(getattr(error, "code", 0) or 0) == 429
    if isinstance(error, urllib.error.URLError):
        return not isinstance(getattr(error, "reason", None), ssl.SSLError)
    return isinstance(error, (TimeoutError, ConnectionError))


def _open_with_one_retry(opener, request, timeout):
    try:
        return opener.open(request, timeout=timeout)
    except Exception as error:  # noqa: BLE001 - wird unten erneut geworfen
        if not _retryable(error):
            raise
        retry_after = 0.0
        if isinstance(error, urllib.error.HTTPError):
            try:
                retry_after = float(error.headers.get("Retry-After") or 0)
            except (TypeError, ValueError, AttributeError):
                retry_after = 0.0
        time.sleep(min(5.0, max(RETRY_PAUSE_SECONDS, retry_after)))
        return opener.open(request, timeout=timeout)


# M1 (12.11.2026): Bezahl- und Login-Datenbanken werden nicht abgerufen und
# zaehlen nicht als Quelle. Treffer der Websuche auf diese Seiten bleiben
# unberuehrt; nur ihre Verwendung als Beleg entfaellt.
BLOCKED_SOURCE_DOMAINS = (
    "crunchbase.com", "dealroom.co", "pitchbook.com", "tracxn.com", "cbinsights.com",
    "northdata.de", "northdata.com", "handelsregister.ai", "linkedin.com", "zoominfo.com",
    "rocketreach.co", "fusionbase.com", "zavia.ai", "companyhouse.de", "registercheck.de",
    "firmenwissen.de", "owler.com", "apollo.io", "signalhire.com", "dnb.com", "f6s.com",
)
BLOCKED_STATUS = "blocked_paid_database"


def is_blocked_source(url: str) -> bool:
    host = (urllib.parse.urlsplit(str(url or "")).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in BLOCKED_SOURCE_DOMAINS)


NEGATIVE_OPERATING = {"acquired", "insolvent", "ceased"}


def apply_operating_rule(candidate) -> None:
    """M5 (12.11.2026): Fortbestand gilt als aktiv, wenn die eigene Website
    erreichbar ist und das Impressum mit Firmenname geprueft wurde, sofern kein
    Gegenbeleg vorliegt (Uebernahme, Insolvenz, Einstellung). Ein Modellurteil
    'active' bleibt; ein negatives Modellurteil wird nie ueberschrieben."""
    status = str(getattr(candidate, "operating_status", "") or "").strip().lower()
    if status in NEGATIVE_OPERATING or status == "active":
        if status == "active" and not getattr(candidate, "operating_status_basis", ""):
            candidate.operating_status_basis = "Modellurteil"
        return
    imp = dict(getattr(candidate, "impressum", None) or {})
    if imp.get("company_name_found") and str(imp.get("url") or "").startswith(("https://", "http://")):
        candidate.operating_status = "active"
        candidate.operating_status_basis = ("Regel M5: eigene Website erreichbar, Impressum mit "
                                            "Firmenname geprueft, kein Gegenbeleg")


class EvidenceResolver:
    def __init__(self, timeout: int = DEFAULT_TIMEOUT,
                 max_document_bytes: int = MAX_DOCUMENT_BYTES,
                 resource_broker=None):
        self.timeout = timeout
        self.max_document_bytes = max_document_bytes
        self.cache: dict[str, dict] = {}
        self.resource_broker = resource_broker

    def attach_resource_broker(self, resource_broker) -> None:
        self.resource_broker = resource_broker

    def _fetch(self, url: str) -> dict:
        if url in self.cache:
            return dict(self.cache[url])
        started = time.perf_counter()
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not _public_host(parsed.hostname or ""):
            result = {"status": "blocked", "error": "keine oeffentliche HTTP(S)-Adresse"}
            self.cache[url] = result
            return dict(result)
        if self.resource_broker:
            allowed, reason = self.resource_broker.begin_resolver_fetch()
            if not allowed:
                return {"status": "not_checked_budget", "error": reason}
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "VeriScout-Evidence-Resolver/1.0 (+research prototype)",
                "Accept": "text/html,application/xhtml+xml,application/pdf,text/plain;q=0.9,*/*;q=0.5",
            },
        )
        try:
            opener = urllib.request.build_opener(
                _NoRedirectHandler(),
                urllib.request.HTTPSHandler(context=source_tls_context()))
            with _open_with_one_retry(opener, request, self.timeout) as response:
                content_length = int(response.headers.get("Content-Length") or 0)
                if content_length > self.max_document_bytes:
                    raise ValueError("Dokument ueberschreitet Abruflimit")
                raw = response.read(self.max_document_bytes + 1)
                if len(raw) > self.max_document_bytes:
                    raise ValueError("Dokument ueberschreitet Abruflimit")
                result = {
                    "status": "resolved",
                    "http_status": int(getattr(response, "status", 200) or 200),
                    "resolved_url": response.geturl(),
                    "content_type": response.headers.get("Content-Type", ""),
                    "content_hash": hashlib.sha256(raw).hexdigest(),
                    "text": _plain_text(raw, response.headers.get("Content-Type", "")),
                }
                if "html" in str(result["content_type"]).lower():
                    result["links"] = _same_site_links(
                        raw.decode("utf-8", errors="replace"), result["resolved_url"])
                if ("pdf" in str(result["content_type"]).lower()
                        or raw[:5] == b"%PDF-"):
                    # PDF-Text wird mit pypdf gelesen; ohne lesbaren Text
                    # (z. B. Scan) bleibt ein eigener Status statt stillem Fehlschlag.
                    result["text_status"] = ("pdf_parsed" if result["text"]
                                             else "pdf_not_parsed")
                normalised_text = _normalise_claim(result["text"])
                result["text_hash"] = hashlib.sha256(
                    normalised_text.encode("utf-8")).hexdigest() if normalised_text else ""
        except urllib.error.HTTPError as error:
            result = {"status": "technical_error", "error": "HTTPError",
                      "http_status": int(getattr(error, "code", 0) or 0),
                      "error_detail": str(getattr(error, "reason", "") or "")[:80]}
        except (urllib.error.URLError, TimeoutError,
                ValueError, OSError) as error:
            result = {"status": "technical_error", "error": type(error).__name__}
        self.cache[url] = result
        if self.resource_broker:
            self.resource_broker.record_resolver_latency(
                (time.perf_counter() - started) * 1000)
        return dict(result)

    def resolve_source(self, source):
        source.verified_excerpt_hashes = []
        source.resolved_at = datetime.datetime.now(
            datetime.timezone.utc).isoformat()
        if not getattr(source, "citation_verified", False):
            source.resolved_status = "blocked"
            source.excerpt_verified = False
            return source
        if is_blocked_source(getattr(source, "url", "")):
            source.resolved_status = BLOCKED_STATUS
            source.excerpt_verified = False
            return source
        result = self._fetch(str(getattr(source, "url", "") or ""))
        source.resolved_status = result.get("status", "technical_error")
        source.resolved_url = result.get("resolved_url", "")
        source.http_status = int(result.get("http_status") or 0)
        source.content_hash = result.get("content_hash", "")
        source.text_hash = result.get("text_hash", "")
        source.canonical_domain = _canonical_domain(
            source.resolved_url or getattr(source, "url", ""))
        explicit_family = (getattr(source, "source_family", "") or
                           getattr(source, "publisher", ""))
        source.source_family = (_normalise_family(explicit_family)
                                or source.canonical_domain)
        document_text = _normalise_claim(result.get("text", ""))
        excerpt = _normalise_claim(getattr(source, "excerpt", ""))
        source.excerpt_hash = hashlib.sha256(
            excerpt.encode("utf-8")).hexdigest() if excerpt else ""
        source.text_status = result.get("text_status", "")
        mode = (excerpt_match_raw(getattr(source, "excerpt", ""), result.get("text", ""))
                if result.get("status") == "resolved" else "")
        if (not mode and result.get("status") == "resolved"
                and str(getattr(source, "excerpt", "") or "").strip()):
            subpage = self._subpage_match(
                str(getattr(source, "url", "") or ""), getattr(source, "excerpt", ""))
            if subpage:
                mode = "subpage"
                source.matched_subpage_url = subpage
        source.relocation = {}
        if not mode and str(getattr(source, "excerpt", "") or "").strip():
            relocated = self._relocate_excerpt(source, result)
            if relocated:
                found_url, reason = relocated
                mode = "relocated"
                page = self.cache.get(found_url, {})
                source.relocation = {"cited_url": str(getattr(source, "url", "") or ""),
                                     "verified_url": found_url, "reason": reason}
                source.matched_subpage_url = found_url
                # Gebunden wird an die Seite, auf der der Auszug wortgleich steht.
                source.resolved_status = "resolved"
                source.resolved_url = page.get("resolved_url") or found_url
                source.http_status = int(page.get("http_status") or 200)
                source.content_hash = page.get("content_hash", "")
                source.text_hash = page.get("text_hash", "")
        source.excerpt_match_mode = mode
        source.excerpt_verified = bool(mode)
        source.matched_context = ""
        if source.excerpt_verified:
            source.verified_excerpt_hashes = [source.excerpt_hash]
            page = (self.cache.get(source.matched_subpage_url, {})
                    if mode in {"subpage", "relocated"} else result)
            first_part = re.split(r"\.\.\.|…|\[\.\.\.\]",
                                  str(getattr(source, "excerpt", "") or ""))[0]
            source.matched_context = matched_context(first_part, page.get("text", ""))
        return source

    def _relocate_excerpt(self, source, result: dict):
        """N1 (12.11.2026): Quellenabgleich.

        Steht ein Auszug nicht auf der zitierten Seite, oder scheiterte deren
        Abruf mit 404, 410 oder einem Verbindungsfehler, wird derselbe Auszug
        wortgleich (Normalisierung wie M3, keine Umschreibung) in allen bereits
        abgerufenen Seiten dieses Resolvers (= desselben Arms) gesucht, gleiche
        Domain zuerst. Bei 404/410 folgen hoechstens RELOCATION_EXTRA_FETCHES
        Ersatzabrufe auf derselben Domain (Startseite, Sprachvariante), die ins
        Abrufbudget zaehlen. Sperrdatenbanken werden nie ersetzt oder genutzt.
        Rueckgabe: (gefundene URL, Grund) oder None.
        """
        url = str(getattr(source, "url", "") or "")
        raw = str(getattr(source, "excerpt", "") or "")
        status = result.get("status")
        code = int(result.get("http_status") or 0)
        if is_blocked_source(url):
            return None
        if status == "resolved":
            reason = "auszug_nicht_auf_zitierter_seite"
        elif status == "technical_error" and (code in (404, 410) or code == 0):
            reason = f"abruf_gescheitert_{code or 'verbindung'}"
        else:
            return None
        cited_domain = _canonical_domain(url)

        def search(pages) -> str:
            for page_url, page in pages:
                if page_url == url or is_blocked_source(page_url):
                    continue
                if page.get("status") != "resolved" or not page.get("text"):
                    continue
                if excerpt_match_raw(raw, page.get("text", "")):
                    return page_url
            return ""

        ordered = sorted(self.cache.items(),
                         key=lambda item: (_canonical_domain(item[0]) != cited_domain, item[0]))
        found = search(ordered)
        if found:
            return found, reason + ("_gleiche_domain" if _canonical_domain(found) == cited_domain
                                    else "_andere_domain")
        if code not in (404, 410):
            return None
        for candidate in _replacement_urls(url)[:RELOCATION_EXTRA_FETCHES]:
            if candidate not in self.cache:
                page = self._fetch(candidate)
                if page.get("status") == "not_checked_budget":
                    break
            found = search([(candidate, self.cache.get(candidate, {}))])
            if found:
                return found, reason + "_ersatzabruf"
        return None

    def _subpage_match(self, url: str, raw_excerpt: str) -> str:
        """Sucht einen nicht gefundenen Auszug auf Unterseiten derselben Website.

        Modelle zitieren oft die Startseite, der Satz steht aber auf einer
        Unterseite (z. B. "Ueber uns", "Technologie", "Impressum"). Geprueft
        werden hoechstens SUBPAGE_LIMIT verlinkte Seiten derselben Domain,
        bevorzugt solche mit typischen Pfadwoertern. Jeder Abruf zaehlt gegen
        das Resolverbudget. Rueckgabe: URL der Fundseite oder "".
        """
        document = self.cache.get(url, {})
        links = list(document.get("links") or [])
        if not links:
            return ""

        def score(link: str) -> int:
            path = urllib.parse.urlsplit(link).path.lower()
            return -sum(keyword in path for keyword in SUBPAGE_KEYWORDS)

        for link in sorted(links, key=score)[:SUBPAGE_LIMIT]:
            page = self._fetch(link)
            if page.get("status") != "resolved":
                continue
            if excerpt_match_raw(raw_excerpt, page.get("text", "")):
                return link
        return ""

    def _verify_claim_excerpts(self, candidate, source) -> None:
        """Prueft jeden atomaren Auszug, nicht nur den allgemeinen Quellenauszug.

        Textvorkommen belegt weder logische Folgerung noch fachliche Eignung.
        Diese mechanische Kontrolle ersetzt keine inhaltliche Annotation.
        """
        url = str(getattr(source, "url", "") or "")
        document = self.cache.get(url, {})
        if document.get("status") != "resolved":
            return
        text = _normalise_claim(document.get("text", ""))
        identifiers = {url, str(getattr(source, "source_id", "") or ""),
                       str(getattr(source, "document_id", "") or "")}
        identifiers.discard("")
        verified = set(getattr(source, "verified_excerpt_hashes", []) or [])
        for claim in getattr(candidate, "evidence_claims", []) or []:
            if not isinstance(claim, dict):
                continue
            if str(claim.get("source_id") or claim.get("source_url") or "") not in identifiers:
                continue
            raw_excerpt = claim.get("excerpt") or source.excerpt
            excerpt = _normalise_claim(raw_excerpt)
            if (excerpt_match_raw(raw_excerpt, document.get("text", ""))
                    or (raw_excerpt and self._subpage_match(url, raw_excerpt))):
                verified.add(hashlib.sha256(excerpt.encode("utf-8")).hexdigest())
        source.verified_excerpt_hashes = sorted(verified)

    @staticmethod
    def _eligible_sources(candidate) -> list:
        return [source for source in
                list(getattr(candidate, "sources", None) or [])
                if getattr(source, "citation_verified", False)]

    def resolve_candidates(self, candidates: list,
                           max_fetches_total: int = 10) -> dict:
        """Prueft Quellen aller Kandidaten mit einem gemeinsamen Round-Robin-Cap.

        SAS und MAS verwenden exakt diese Routine. Ein Gesamtlimit wird damit
        nicht versehentlich zu vier Abrufen *je* SAS-Kandidat, aber zwei Abrufen
        *je* MAS-Kandidat. Round Robin verhindert zusaetzlich, dass der erste
        Rang das gesamte Abrufbudget verbraucht. Alle uebrig gebliebenen,
        nativen Quellen erhalten den auswertbaren Status
        ``not_checked_budget``.
        """
        rows = list(candidates or [])
        queues = [self._eligible_sources(candidate) for candidate in rows]
        positions = [0 for _ in rows]
        attempted = 0
        cap = max(0, int(max_fetches_total))

        while True:
            progressed = False
            for index, queue in enumerate(queues):
                if positions[index] >= len(queue):
                    continue
                source = queue[positions[index]]
                positions[index] += 1
                progressed = True
                url = str(getattr(source, "url", "") or "")
                if url in self.cache:
                    self.resolve_source(source)
                elif attempted < cap:
                    attempted += 1
                    self.resolve_source(source)
                else:
                    source.resolved_status = "not_checked_budget"
                    source.excerpt_verified = False
                    source.verified_excerpt_hashes = []
                self._verify_claim_excerpts(rows[index], source)
            if not progressed:
                break

        for index, queue in enumerate(queues):
            for source in queue[positions[index]:]:
                if getattr(source, "resolved_status", "not_checked") in {
                        "", "not_checked"}:
                    source.resolved_status = "not_checked_budget"
                    source.excerpt_verified = False
        # R2: Impressum je Kandidat deterministisch aus dem verbleibenden
        # Abrufbudget pruefen, fuer beide Architekturen gleich.
        for candidate in rows:
            attempted += self._resolve_impressum(candidate, max(0, cap - attempted))
            apply_operating_rule(candidate)
        # N1, zweiter Durchgang: erst jetzt liegen alle Seiten dieses Arms vor.
        # Nicht bestaetigte Quellen werden gegen den vollstaendigen Abrufspeicher
        # erneut abgeglichen; bereits geladene Seiten kosten keinen Abruf.
        for candidate in rows:
            for source in candidate.sources or []:
                if getattr(source, "excerpt_verified", False) or not getattr(source, "citation_verified", False):
                    continue
                if getattr(source, "resolved_status", "") not in {"resolved", "technical_error"}:
                    continue
                self.resolve_source(source)
        # Die Rueckgabe beschreibt den finalen Zustand aller zulaessigen
        # Quellen. Damit wird auch eine Budgetablehnung gezaehlt, die waehrend
        # eines bereits begonnenen Round-Robin-Slots im Broker entsteht.
        eligible = [source for queue in queues for source in queue]
        resolved = sum(getattr(source, "resolved_status", "") == "resolved"
                       for source in eligible)
        excerpts = sum(bool(getattr(source, "excerpt_verified", False))
                       for source in eligible)
        technical_errors = sum(
            getattr(source, "resolved_status", "") == "technical_error"
            for source in eligible)
        not_checked_budget = sum(
            getattr(source, "resolved_status", "") == "not_checked_budget"
            for source in eligible)
        return {
            "checked": attempted,
            "resolved": resolved,
            "excerpt_verified": excerpts,
            "technical_errors": technical_errors,
            "not_checked_budget": not_checked_budget,
            "max_fetches_total": cap,
            "allocation": "candidate_round_robin_unique_url_v2",
        }

    def _resolve_impressum(self, candidate, budget: int) -> int:
        """Ruft hoechstens zwei Impressum-Adressen ab; liefert verbrauchte Abrufe."""
        website = str(getattr(candidate, "official_url", "") or getattr(candidate, "website", "") or "")
        parts = urllib.parse.urlsplit(website if "://" in website else "https://" + website)
        if not parts.hostname or not hasattr(candidate, "impressum"):
            return 0
        base = f"{parts.scheme or 'https'}://{parts.hostname}"
        cached_links = []
        for url, result in self.cache.items():
            if urllib.parse.urlsplit(url).hostname == parts.hostname:
                cached_links += [link for link in result.get("links") or []
                                 if re.search(r"impressum|imprint|legal", link, re.I)]
        urls = list(dict.fromkeys(cached_links[:1] + [base + path for path in IMPRESSUM_PATHS]))
        used = 0
        for url in urls:
            if url not in self.cache:
                if used >= min(2, budget):
                    break
                used += 1
            result = self._fetch(url)
            if result.get("status") != "resolved":
                continue
            parsed = parse_impressum(result.get("text", ""), getattr(candidate, "name", ""))
            if parsed["register"] or parsed["company_name_found"]:
                candidate.impressum = {"url": result.get("resolved_url") or url, **parsed}
                break
        return used

    def resolve_candidate(self, candidate, max_fetches: int = 10) -> dict:
        """Rueckwaertskompatibler Ein-Kandidaten-Aufruf."""
        result = self.resolve_candidates([candidate], max_fetches_total=max_fetches)
        result["max_fetches"] = max_fetches
        return result
