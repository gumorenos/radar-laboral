from __future__ import annotations

import argparse
import logging
import os
import time

from .collectors.el_peruano_search import collect

DEFAULT_INTERVAL_SECONDS = 6 * 60 * 60
MIN_INTERVAL_SECONDS = 60 * 60


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ejecuta la sincronización de Radar Laboral periódicamente"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=_env_int("RADAR_SYNC_INTERVAL_SECONDS", DEFAULT_INTERVAL_SECONDS),
        help="Intervalo entre sincronizaciones en segundos (mínimo 3600)",
    )
    parser.add_argument(
        "--initial-delay",
        type=int,
        default=_env_int("RADAR_SYNC_INITIAL_DELAY_SECONDS", 15),
        help="Espera inicial antes de la primera sincronización",
    )
    parser.add_argument(
        "--no-pdf",
        action="store_true",
        help="Sincroniza metadatos sin descargar PDFs",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    interval = max(MIN_INTERVAL_SECONDS, args.interval)
    initial_delay = max(0, args.initial_delay)

    if initial_delay:
        logging.info("Primera sincronización en %s segundos", initial_delay)
        time.sleep(initial_delay)

    while True:
        started = time.monotonic()
        try:
            records = collect(download_pdfs=not args.no_pdf)
            pdf_count = sum(1 for item in records if item.get("pdf_path"))
            logging.info(
                "Sincronización completada: %s registros, %s PDFs disponibles",
                len(records),
                pdf_count,
            )
        except Exception:
            logging.exception("Falló la sincronización; se reintentará en el siguiente ciclo")

        elapsed = time.monotonic() - started
        sleep_for = max(60, interval - int(elapsed))
        logging.info("Próxima sincronización en %s segundos", sleep_for)
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()
