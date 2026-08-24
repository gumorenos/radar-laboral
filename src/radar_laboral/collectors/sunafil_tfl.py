from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from radar_laboral.case_law import get_case_law, upsert_case_law
from radar_laboral.db import data_dir, finish_sync_run, init_db, start_sync_run

SOURCE = "SUNAFIL TFL"
COURT = "Tribunal de Fiscalización Laboral - Sala Plena"
DOCUMENT_TYPE = "Resolución de Sala Plena"
BASE_URL = "https://www.gob.pe"
LIST_URL = f"{BASE_URL}/institucion/sunafil/normas-legales/tipos/145-resolucion-de-sala-plena"
DEFAULT_MAX_PAGES = 1
MAX_PAGES = 20

DETAIL_RE = re.compile(
    r"^/institucion/sunafil/normas-legales/(?P<resource_id>\d+)-(?P<slug>[^/?#]+)$",
    re.I,
)
HEADING_RE = re.compile(
    r"Resoluci[oó]n\s+de\s+Sala\s+Plena\s+N[.°º\s]*\s*(?P<number>[^\n]+?)(?:\s*$)",
    re.I,
)
SPANISH_DATE_RE = re.compile(
    r"\b(?P<day>\d{1,2})\s+de\s+(?P<month>enero|febrero|marzo|abril|mayo|junio|julio|agosto|setiembre|septiembre|octubre|noviembre|diciembre)\s+de\s+(?P<year>\d{4})\b",
    re.I,
)
MANDATORY_PRECEDENT_RE = re.compile(
    r"precedent(?:e|es)\s+administrativ(?:o|os|a|as)[^.]{0,160}?observancia\s+obligatoria",
    re.I | re.S,
)
MANDATORY_CRITERIA_RE = re.compile(
    r"criteri(?:o|os)[^.]{0,180}?observancia\s+obligatoria",
    re.I | re.S,
)
MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "setiembre": 9,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


class TflCollectorError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _iso_spanish_date(match: re.Match[str]) -> str:
    return datetime(
        int(match.group("year")),
        MONTHS[match.group("month").lower()],
        int(match.group("day")),
    ).date().isoformat()


def _allowed_gob_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "gob.pe" or host.endswith(".gob.pe")


def _detail_match(url: str) -> re.Match[str] | None:
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() not in {"gob.pe", "www.gob.pe"}:
        return None
    return DETAIL_RE.match(parsed.path.rstrip("/"))


def _number_from_heading(value: str) -> str | None:
    match = HEADING_RE.search(_clean(value))
    return _clean(match.group("number")) if match else None


def _binding_level(summary: str | None) -> str | None:
    if not summary:
        return None
    if MANDATORY_PRECEDENT_RE.search(summary):
        return "precedente administrativo de observancia obligatoria"
    if MANDATORY_CRITERIA_RE.search(summary):
        return "criterio de observancia obligatoria"
    return None


def _card_for(anchor: Tag) -> Tag:
    node: Tag | None = anchor
    while node is not None:
        text = _clean(node.get_text(" ", strip=True))
        if SPANISH_DATE_RE.search(text) and ("Descargar" in text or "Leer más" in text):
            return node
        parent = node.parent
        node = parent if isinstance(parent, Tag) else None
    return anchor.parent if isinstance(anchor.parent, Tag) else anchor


def _summary_from_card(card: Tag, heading: str) -> str | None:
    candidates: list[str] = []
    for node in card.find_all("p"):
        text = _clean(node.get_text(" ", strip=True))
        if len(text) < 25 or text == heading or SPANISH_DATE_RE.fullmatch(text):
            continue
        candidates.append(text)
    return max(candidates, key=len) if candidates else None


def _pdf_from_node(node: Tag, base_url: str) -> str | None:
    for anchor in node.find_all("a", href=True):
        href = urljoin(base_url, str(anchor.get("href", "")).strip())
        text = _clean(anchor.get_text(" ", strip=True)).casefold()
        path = urlparse(href).path.casefold()
        if _allowed_gob_url(href) and (path.endswith(".pdf") or "descargar" in text):
            return href
    return None


def _has_next_sheet(soup: BeautifulSoup, current_sheet: int) -> bool:
    for anchor in soup.find_all("a", href=True):
        href = urljoin(LIST_URL, str(anchor.get("href", "")).strip())
        for value in parse_qs(urlparse(href).query).get("sheet", []):
            if value.isdigit() and int(value) > current_sheet:
                return True
    return False


def parse_listing_html(
    html: str,
    *,
    current_sheet: int = 1,
    captured_at: str | None = None,
) -> tuple[list[dict[str, object]], bool]:
    soup = BeautifulSoup(html, "html.parser")
    captured_at = captured_at or _utc_now()
    records: dict[str, dict[str, object]] = {}

    for anchor in soup.find_all("a", href=True):
        official_url = urljoin(BASE_URL, str(anchor.get("href", "")).strip())
        detail = _detail_match(official_url)
        if detail is None:
            continue
        heading = _clean(anchor.get_text(" ", strip=True))
        number = _number_from_heading(heading)
        if not number:
            continue

        card = _card_for(anchor)
        date_match = SPANISH_DATE_RE.search(_clean(card.get_text(" ", strip=True)))
        if date_match is None:
            continue
        summary = _summary_from_card(card, heading)
        resource_id = detail.group("resource_id")
        records[resource_id] = {
            "id": f"sunafil-tfl:{resource_id}",
            "source": SOURCE,
            "court": COURT,
            "document_type": DOCUMENT_TYPE,
            "number": number,
            "docket_number": None,
            "title": heading,
            "summary": summary,
            "decision_date": None,
            "publication_date": _iso_spanish_date(date_match),
            "topic": None,
            "binding_level": _binding_level(summary),
            "official_url": official_url,
            "pdf_url": _pdf_from_node(card, official_url),
            "pdf_path": None,
            "sha256": None,
            "captured_at": captured_at,
            "updated_at": captured_at,
        }

    ordered = sorted(
        records.values(),
        key=lambda item: (str(item.get("publication_date") or ""), str(item["id"])),
        reverse=True,
    )
    return ordered, _has_next_sheet(soup, current_sheet)


def _detail_heading(soup: BeautifulSoup) -> str | None:
    for node in soup.find_all(["h1", "h2", "h3"]):
        text = _clean(node.get_text(" ", strip=True))
        if _number_from_heading(text):
            return text
    return None


def _detail_summary(soup: BeautifulSoup, heading: str | None) -> str | None:
    main = soup.find("main") or soup
    candidates: list[str] = []
    for node in main.find_all("p"):
        text = _clean(node.get_text(" ", strip=True))
        if len(text) < 35 or text == heading or SPANISH_DATE_RE.fullmatch(text):
            continue
        lowered = text.casefold()
        if "plataforma digital única" in lowered or "¿no encuentras lo que buscas?" in lowered:
            continue
        candidates.append(text)
    if candidates:
        return max(candidates, key=len)

    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        text = _clean(str(meta.get("content")))
        if len(text) >= 35:
            return text
    return None


def parse_detail_html(
    html: str,
    official_url: str,
    *,
    captured_at: str | None = None,
) -> dict[str, object]:
    detail = _detail_match(official_url)
    if detail is None:
        raise TflCollectorError(f"URL de detalle SUNAFIL no reconocida: {official_url}")

    soup = BeautifulSoup(html, "html.parser")
    heading = _detail_heading(soup)
    if heading is None:
        raise TflCollectorError(f"No se encontró el encabezado de Sala Plena en {official_url}")
    number = _number_from_heading(heading)
    if not number:
        raise TflCollectorError(f"No se pudo extraer el número de resolución en {official_url}")

    main = soup.find("main") or soup
    date_match = SPANISH_DATE_RE.search(_clean(main.get_text(" ", strip=True)))
    if date_match is None:
        raise TflCollectorError(f"No se encontró fecha oficial en {official_url}")
    summary = _detail_summary(soup, heading)
    captured_at = captured_at or _utc_now()
    resource_id = detail.group("resource_id")

    return {
        "id": f"sunafil-tfl:{resource_id}",
        "source": SOURCE,
        "court": COURT,
        "document_type": DOCUMENT_TYPE,
        "number": number,
        "docket_number": None,
        "title": heading,
        "summary": summary,
        "decision_date": None,
        "publication_date": _iso_spanish_date(date_match),
        "topic": None,
        "binding_level": _binding_level(summary),
        "official_url": official_url,
        "pdf_url": _pdf_from_node(main, official_url),
        "pdf_path": None,
        "sha256": None,
        "captured_at": captured_at,
        "updated_at": captured_at,
    }


def fetch_listing_page(
    session: requests.Session,
    sheet: int,
) -> tuple[list[dict[str, object]], bool]:
    response = session.get(LIST_URL, params={"sheet": sheet}, timeout=30)
    response.raise_for_status()
    return parse_listing_html(response.text, current_sheet=sheet)


def fetch_detail(session: requests.Session, official_url: str) -> dict[str, object]:
    response = session.get(official_url, timeout=30)
    response.raise_for_status()
    if not _allowed_gob_url(response.url):
        raise TflCollectorError(f"SUNAFIL redirigió fuera de gob.pe: {response.url}")
    return parse_detail_html(response.text, response.url)


def _pdf_digest(path: Path) -> str | None:
    try:
        with path.open("rb") as handle:
            first = handle.read(64 * 1024)
            if not first.startswith(b"%PDF"):
                return None
            digest = hashlib.sha256()
            digest.update(first)
            for chunk in iter(lambda: handle.read(64 * 1024), b""):
                digest.update(chunk)
            return digest.hexdigest()
    except OSError:
        return None


def _restore_pdf(record: dict[str, object], destination: Path, relative_path: Path) -> bool:
    existing = get_case_law(str(record["id"]))
    if existing is not None and existing["pdf_path"]:
        stored = Path(existing["pdf_path"])
        if not stored.is_absolute():
            stored = data_dir() / stored
        digest = _pdf_digest(stored)
        expected = str(existing["sha256"] or "")
        if digest and expected and digest != expected:
            try:
                stored.unlink()
            except OSError:
                pass
            digest = None
        if digest:
            record["pdf_path"] = str(existing["pdf_path"])
            record["sha256"] = digest
            if existing["pdf_url"]:
                record["pdf_url"] = str(existing["pdf_url"])
            return True

    digest = _pdf_digest(destination)
    if digest:
        record["pdf_path"] = relative_path.as_posix()
        record["sha256"] = digest
        return True
    return False


def cache_pdf(session: requests.Session, record: dict[str, object]) -> None:
    pdf_url = str(record.get("pdf_url") or "")
    if not pdf_url or not _allowed_gob_url(pdf_url):
        return

    year = str(record.get("publication_date") or "unknown")[:4]
    resource_id = str(record["id"]).removeprefix("sunafil-tfl:")
    relative_path = Path("pdfs") / "sunafil-tfl" / year / f"{resource_id}.pdf"
    destination = data_dir() / relative_path
    if _restore_pdf(record, destination, relative_path):
        return

    with session.get(pdf_url, timeout=45, stream=True, allow_redirects=True) as response:
        response.raise_for_status()
        if not _allowed_gob_url(response.url):
            return
        iterator = response.iter_content(chunk_size=64 * 1024)
        try:
            first = next(iterator)
        except StopIteration:
            return
        content_type = response.headers.get("content-type", "").casefold()
        if "application/pdf" not in content_type and not first.startswith(b"%PDF"):
            return

        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        try:
            with destination.open("wb") as handle:
                digest.update(first)
                handle.write(first)
                for chunk in iterator:
                    if chunk:
                        digest.update(chunk)
                        handle.write(chunk)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        resolved_url = response.url

    record["pdf_url"] = resolved_url
    record["pdf_path"] = relative_path.as_posix()
    record["sha256"] = digest.hexdigest()


def default_catalog_path() -> Path:
    configured = os.getenv("RADAR_CASE_LAW_CATALOG_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return data_dir() / "catalog" / "case_law.jsonl"


def merge_catalog(records: list[dict[str, object]], path: Path) -> None:
    current: dict[str, dict[str, object]] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                current[str(item["id"])] = item

    for record in records:
        key = str(record["id"])
        previous = current.get(key, {})
        merged = dict(previous)
        for field, value in record.items():
            if value is not None:
                merged[field] = value
        if previous.get("captured_at"):
            merged["captured_at"] = previous["captured_at"]
        current[key] = merged

    ordered = sorted(
        current.values(),
        key=lambda item: (str(item.get("publication_date") or ""), str(item.get("id") or "")),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in ordered),
        encoding="utf-8",
    )


def _merge_detail(listing: dict[str, object], detail: dict[str, object]) -> dict[str, object]:
    merged = dict(listing)
    for key, value in detail.items():
        if value is not None:
            merged[key] = value
    merged["captured_at"] = listing.get("captured_at") or detail.get("captured_at")
    return merged


def collect(
    *,
    download_pdfs: bool = True,
    max_pages: int = DEFAULT_MAX_PAGES,
    refresh_details: bool = False,
    catalog_path: Path | None = None,
    page_delay_seconds: float = 0.2,
    detail_delay_seconds: float = 0.1,
) -> list[dict[str, object]]:
    max_pages = max(1, min(int(max_pages), MAX_PAGES))
    catalog_path = catalog_path or default_catalog_path()
    init_db()
    run_id = start_sync_run(SOURCE)
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "radar-laboral/0.1 (+https://github.com/gumorenos/radar-laboral)",
            "Accept-Language": "es-PE,es;q=0.9",
        }
    )

    stored: list[dict[str, object]] = []
    try:
        discovered: dict[str, dict[str, object]] = {}
        for sheet in range(1, max_pages + 1):
            page_records, has_next = fetch_listing_page(session, sheet)
            if sheet == 1 and not page_records:
                raise TflCollectorError(
                    "SUNAFIL TFL no devolvió resoluciones reconocibles en la primera página."
                )
            new_count = 0
            for record in page_records:
                key = str(record["id"])
                if key not in discovered:
                    new_count += 1
                discovered[key] = record
            if not has_next or not page_records or new_count == 0:
                break
            if sheet < max_pages and page_delay_seconds > 0:
                time.sleep(page_delay_seconds)

        for index, listing in enumerate(discovered.values()):
            record = dict(listing)
            existing = get_case_law(str(record["id"]))
            needs_detail = (
                refresh_details
                or existing is None
                or not existing["summary"]
                or not existing["pdf_url"]
            )
            if needs_detail:
                record = _merge_detail(
                    record,
                    fetch_detail(session, str(record["official_url"])),
                )
                if detail_delay_seconds > 0 and index < len(discovered) - 1:
                    time.sleep(detail_delay_seconds)
            elif existing is not None:
                for field in (
                    "summary",
                    "binding_level",
                    "pdf_url",
                    "pdf_path",
                    "sha256",
                    "topic",
                ):
                    if existing[field] is not None:
                        record[field] = existing[field]
                if existing["captured_at"]:
                    record["captured_at"] = existing["captured_at"]

            if download_pdfs:
                try:
                    cache_pdf(session, record)
                except requests.RequestException:
                    pass
            stored.append(upsert_case_law(record))

        if stored:
            merge_catalog(stored, catalog_path)
        pdf_count = sum(1 for item in stored if item.get("pdf_path"))
        latest_date = max(
            (
                str(item.get("publication_date"))
                for item in stored
                if item.get("publication_date")
            ),
            default=None,
        )
        finish_sync_run(
            run_id,
            status="success",
            records_seen=len(stored),
            pdf_count=pdf_count,
            latest_publication_date=latest_date,
        )
        return stored
    except Exception as exc:
        finish_sync_run(
            run_id,
            status="failed",
            records_seen=len(stored),
            pdf_count=sum(1 for item in stored if item.get("pdf_path")),
            error=f"{type(exc).__name__}: {exc}"[:2000],
        )
        raise
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Sincroniza Resoluciones de Sala Plena del Tribunal de Fiscalización Laboral de SUNAFIL"
        )
    )
    pages = parser.add_mutually_exclusive_group()
    pages.add_argument(
        "--pages",
        type=int,
        default=DEFAULT_MAX_PAGES,
        help="Número de páginas del listado a procesar",
    )
    pages.add_argument(
        "--all-pages",
        action="store_true",
        help="Recorre todo el histórico disponible",
    )
    parser.add_argument("--no-pdf", action="store_true", help="No descarga PDFs oficiales")
    parser.add_argument(
        "--refresh-details",
        action="store_true",
        help="Vuelve a consultar el detalle de registros ya almacenados",
    )
    parser.add_argument("--catalog", type=Path, default=default_catalog_path())
    parser.add_argument("--page-delay", type=float, default=0.2)
    parser.add_argument("--detail-delay", type=float, default=0.1)
    args = parser.parse_args()

    records = collect(
        download_pdfs=not args.no_pdf,
        max_pages=MAX_PAGES if args.all_pages else args.pages,
        refresh_details=args.refresh_details,
        catalog_path=args.catalog,
        page_delay_seconds=max(0.0, args.page_delay),
        detail_delay_seconds=max(0.0, args.detail_delay),
    )
    pdf_count = sum(1 for item in records if item.get("pdf_path"))
    mandatory = sum(1 for item in records if item.get("binding_level"))
    print(
        f"SUNAFIL TFL: {len(records)} resoluciones; "
        f"{mandatory} con fuerza/alcance explícito; {pdf_count} PDF almacenados."
    )


if __name__ == "__main__":
    main()
