from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import date

from .collectors.el_peruano_history import backfill
from .db import (
    SYNC_REQUEST_KIND_BACKFILL,
    claim_next_sync_request,
    finish_sync_request,
    init_db,
    recover_running_sync_requests,
)

DEFAULT_POLL_SECONDS = 30
MIN_POLL_SECONDS = 5


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def process_one_request() -> bool:
    request_row = claim_next_sync_request()
    if request_row is None:
        return False

    request_id = int(request_row["id"])
    kind = str(request_row["kind"])
    try:
        if kind != SYNC_REQUEST_KIND_BACKFILL:
            raise ValueError(f"Tipo de solicitud no soportado: {kind}")

        start_date = date.fromisoformat(str(request_row["start_date"]))
        end_date = date.fromisoformat(str(request_row["end_date"]))
        download_pdfs = bool(request_row["download_pdfs"])
        logging.info(
            "Procesando carga histórica #%s: %s a %s; PDFs=%s; solo faltantes",
            request_id,
            start_date,
            end_date,
            download_pdfs,
        )
        records = backfill(
            start_date,
            end_date,
            download_pdfs=download_pdfs,
            skip_complete_days=True,
        )
        finish_sync_request(request_id, status="success")
        logging.info(
            "Carga histórica #%s completada: %s registros procesados",
            request_id,
            len(records),
        )
    except Exception as exc:
        finish_sync_request(
            request_id,
            status="failed",
            error=f"{type(exc).__name__}: {exc}"[:2000],
        )
        logging.exception("Falló la carga histórica #%s", request_id)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Procesa solicitudes persistentes de carga histórica de Radar Laboral"
    )
    parser.add_argument(
        "--poll",
        type=int,
        default=_env_int("RADAR_WORKER_POLL_SECONDS", DEFAULT_POLL_SECONDS),
        help="Segundos entre consultas de la cola cuando no hay trabajo",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Procesa como máximo una solicitud y termina",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    init_db()
    recovered = recover_running_sync_requests()
    if recovered:
        logging.warning("Se reencolaron %s solicitudes interrumpidas", recovered)

    poll = max(MIN_POLL_SECONDS, args.poll)
    while True:
        processed = process_one_request()
        if args.once:
            return
        if not processed:
            time.sleep(poll)


if __name__ == "__main__":
    main()
