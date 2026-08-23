from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from radar_laboral.db import data_dir, init_db, upsert_norm

SOURCE = "El Peruano"
BASE_URL = "https://diariooficial.elperuano.pe"
DAILY_URL = f"{BASE_URL}/Normas/LoadNormasLegales?Length=0"
ALLOWED_PDF_HOST_SUFFIX = ".elperuano.pe"
DEVICE_RE = re.compile(r"/dispositivo/NL/(?P<op>[0-9]+-[0-9]+)(?:/)?$", re.I)
NUMBER_RE = re.compile(r"^(?P<document_type>.+?)\s+N(?:°|º|\.º)\s*(?P<number>.+)$", re.I)
DATE_RE = re.compile(r"Fecha:\s*(?P<date>\d{2}/\d{2}/\d{4})", re.I)
URL_RE = re.compile(r"https?://[^\"'<>\s]+", re.I)


class CollectorError(RuntimeError):
    pass


def _iso_date(value: str) -> str:
    return datetime.strptime(value, "%d/%m/%Y").date().isoformat()


def _allowed_el_peruano_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "elperuano.pe" or host.endswith(ALLOWED_PDF_HOST_SUFFIX)


def _card_for(anchor: Tag) -> Tag:
    node: Tag | None = anchor
    while node is not None:
        text = node.get_text("\n", strip=True)
        if "Fecha:" in text and "Descarga individual" in text:
            return node
        parent = node.parent
        node = parent if isinstance(parent, Tag) else None
    return anchor.parent if isinstance(anchor.parent, Tag) else anchor


def _issuer_from_card(card: Tag, anchor: Tag) -> str | None:
    for heading_name in ("h3", "h4"):
        for heading in card.find_all(heading_name):
            text = heading.get_text(" ", strip=True)
            if text and text != anchor.get_text(" ", strip=True):
                return text
    return None


def _summary_from_card(card: Tag, *, issuer: str | None, heading: str) -> str | None:
    ignored_exact = {
        issuer or "",
        heading,
        "Descarga individual",
        "Todo el cuadernillo",
        "Edición Extraordinaria",
    }
    for line in card.get_text("\n", strip=True).splitlines():
        line = line.strip()
        if not line or line in ignored_exact:
            continue
        if DATE_RE.fullmatch(line):
            continue
        if line.lower().startswith("fecha:"):
            continue
        if line.lower().startswith("descargar"):
            continue
        if line.lower().startswith("todo el cuadernillo"):
            continue
        return line
    return None


def parse_daily_html(html: str, *, captured_at: str | None = None) -> list[dict[str, str | None]]:
    soup = BeautifulSoup(html, "html.parser")
    captured_at = captured_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    records: dict[str, dict[str, str | None]] = {}

    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", "")).strip()
        match = DEVICE_RE.search(urlparse(urljoin(BASE_URL, href)).path)
        if not match:
            continue

        op = match.group("op")
        heading = anchor.get_text(" ", strip=True)
        if not heading:
            continue

        card = _card_for(anchor)
        card_text = card.get_text("\n", strip=True)
        date_match = DATE_RE.search(card_text)
        if not date_match:
            continue

        number_match = NUMBER_RE.match(heading)
        document_type = number_match.group("document_type").strip() if number_match else None
        number = number_match.group("number").strip() if number_match else heading
        issuer = _issuer_from_card(card, anchor)
        sumilla = _summary_from_card(card, issuer=issuer, heading=heading)
        official_url = urljoin("https://busquedas.elperuano.pe", href)

        records[op] = {
            "id": f"elperuano:{op}",
            "source": SOURCE,
            "document_type": document_type,
            "number": number,
            "title": sumilla or heading,
            "summary": None,
            "publication_date": _iso_date(date_match.group("date")),
            "effective_date": None,
            "issuer": issuer,
            "topic": None,
            "status": None,
            "official_url": official_url,
            "pdf_url": official_url.rstrip("/") + "/pdf",
            "pdf_path": None,
            "sha256": None,
            "captured_at": captured_at,
            "updated_at": captured_at,
        }

    return sorted(records.values(), key=lambda item: (item["publication_date"] or "", item["id"] or ""))


def _looks_like_pdf_candidate(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    query = parsed.query.lower()
    return (
        host.startswith("epdoc")
        or path.endswith(".pdf")
        or "vistanl" in path
        or "descarga" in path
        or "referencias=" in query
    )


def _candidate_pdf_urls(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[str] = []

    for tag in soup.find_all(["a", "iframe", "embed", "object", "source"]):
        for attr in ("href", "src", "data"):
            raw = tag.get(attr)
            if not raw:
                continue
            url = urljoin(base_url, str(raw).strip())
            if _allowed_el_peruano_url(url) and _looks_like_pdf_candidate(url):
                candidates.append(url)

    for raw in URL_RE.findall(html):
        url = raw.replace("&amp;", "&")
        if _allowed_el_peruano_url(url) and _looks_like_pdf_candidate(url):
            candidates.append(url)

    unique: list[str] = []
    seen: set[str] = set()
    for url in candidates:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def _download_if_pdf(session: requests.Session, url: str, destination: Path) -> tuple[str, str] | None:
    if not _allowed_el_peruano_url(url):
        return None

    with session.get(url, timeout=45, stream=True, allow_redirects=True) as response:
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        iterator = response.iter_content(chunk_size=64 * 1024)
        try:
            first = next(iterator)
        except StopIteration:
            return None

        is_pdf = "application/pdf" in content_type or first.startswith(b"%PDF")
        if not is_pdf:
            return None

        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        with destination.open("wb") as handle:
            digest.update(first)
            handle.write(first)
            for chunk in iterator:
                if not chunk:
                    continue
                digest.update(chunk)
                handle.write(chunk)

        return response.url, digest.hexdigest()


def cache_pdf(session: requests.Session, record: dict[str, str | None]) -> None:
    viewer_url = record.get("pdf_url")
    if not viewer_url:
        return

    publication_date = record.get("publication_date") or "unknown"
    year = publication_date[:4]
    op = str(record["id"]).split(":", 1)[1]
    relative_path = Path("pdfs") / "elperuano" / year / f"{op}.pdf"
    destination = data_dir() / relative_path

    direct = _download_if_pdf(session, viewer_url, destination)
    if direct:
        record["pdf_url"], record["sha256"] = direct
        record["pdf_path"] = relative_path.as_posix()
        return

    response = session.get(viewer_url, timeout=30)
    response.raise_for_status()
    for candidate in _candidate_pdf_urls(response.text, response.url):
        downloaded = _download_if_pdf(session, candidate, destination)
        if downloaded:
            record["pdf_url"], record["sha256"] = downloaded
            record["pdf_path"] = relative_path.as_posix()
            return


def merge_catalog(records: list[dict[str, str | None]], path: Path) -> None:
    current: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            current[item["id"]] = item

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

    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(
        current.values(),
        key=lambda item: (item.get("publication_date") or "", item.get("id") or ""),
    )
    path.write_text(
        "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in ordered),
        encoding="utf-8",
    )


def collect(*, download_pdfs: bool = True, catalog_path: Path = Path("catalog/norms.jsonl")) -> list[dict[str, str | None]]:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "radar-laboral/0.1 (+https://github.com/gumorenos/radar-laboral)",
        "Accept-Language": "es-PE,es;q=0.9",
    })

    response = session.get(DAILY_URL, timeout=30)
    response.raise_for_status()
    records = parse_daily_html(response.text)
    if not records:
        raise CollectorError("El Peruano no devolvió dispositivos reconocibles; se evita escribir un catálogo vacío.")

    init_db()
    for record in records:
        if download_pdfs:
            try:
                cache_pdf(session, record)
            except requests.RequestException:
                # El registro sigue siendo útil y conserva el visor oficial aun si el PDF falla.
                pass
        upsert_norm(record)

    merge_catalog(records, catalog_path)
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Sincroniza las normas del día desde El Peruano")
    parser.add_argument("--no-pdf", action="store_true", help="No intenta descargar los PDF oficiales")
    parser.add_argument("--catalog", type=Path, default=Path("catalog/norms.jsonl"))
    args = parser.parse_args()

    records = collect(download_pdfs=not args.no_pdf, catalog_path=args.catalog)
    pdf_count = sum(1 for item in records if item.get("pdf_path"))
    print(f"El Peruano: {len(records)} registros sincronizados; {pdf_count} PDF almacenados.")


if __name__ == "__main__":
    main()
