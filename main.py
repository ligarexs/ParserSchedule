"""
Точка входа: скачать -> разобрать -> склеить с кэшем -> записать в таблицу.

Запуск:
    см. README.md
"""

from __future__ import annotations

import argparse
import logging
import sys

from config import GROUP, WEEK_LABEL
from parser import ParseError, parse_file
from renderer import build_grid
from week_cache import merge_week, save_cache

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("run.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("schedule")


def main() -> int:
    arguments = argparse.ArgumentParser()
    arguments.add_argument("--force", action="store_true")
    arguments.add_argument("--dry-run", action="store_true")
    arguments.add_argument("--file")
    args = arguments.parse_args()

    if args.file:
        path, changed = args.file, True
    else:
        from fetcher import FetchError, fetch
        try:
            path, changed = fetch()
        except (FetchError, Exception) as exc:  # noqa: BLE001 — падать нельзя, это фон
            logger.error("Не удалось получить файл с сайта: %s", exc)
            return 1
        logger.info("Файл: %s (%s)", path, "обновился" if changed else "без изменений")

    if not changed and not args.force:
        logger.info("Расписание не менялось, таблицу не трогаю")
        return 0

    try:
        lessons, covered_days = parse_file(path, GROUP)
    except ParseError as exc:
        logger.error("Разбор не удался: %s", exc)
        return 1

    logger.info("Разобрано пар: %d, дни в файле: %s", len(lessons), ", ".join(covered_days))
    if not lessons:
        logger.warning("Файл разобран, но пар не найдено — таблицу не перезаписываю")
        return 1

    week = merge_week(lessons, covered_days)
    grid = build_grid(week, WEEK_LABEL)

    if args.dry_run:
        for row in grid.rows:
            logger.info(" | ".join(cell.text[:34].ljust(34) for cell in row))
        return 0

    from sheets_writer import write_grid
    try:
        write_grid(grid)
    except Exception:  # noqa: BLE001
        logger.exception("Запись в таблицу не удалась")
        return 1

    save_cache(week)
    logger.info("Таблица обновлена")
    return 0


if __name__ == "__main__":
    sys.exit(main())
