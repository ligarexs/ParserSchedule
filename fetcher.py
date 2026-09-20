"""
    Скачивание файла расписания с сайта университета.
    Отслеживание обновлений сделано по содержимому файла (sha256),
    не по имени файла
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re

import requests
from bs4 import BeautifulSoup

from config import COURSE, REQUEST_TIMEOUT, SCHEDULE_DIR, SCHEDULE_URL

logger = logging.getLogger(__name__)

STATE_PATH = "fetch_state.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

COURSE_PATTERNS = {
    "3 курс 4 года": [
        r"(?<!\d)3[\s_-]*к\D{0,5}4[\s_-]*г(?!\d)",     # 3к4г, 3-к-4-г, 3К4Г_ВТ ...
        r"(?<!\d)3[\s_-]*курс",                        # 3-курс-, 3 курс, 3_курс ...
        r"(?<!\d)3[\s_-]*k[\s_-]*4[\s_-]*g(?!\d)",     # латиница: 3k4g
    ],
}


class FetchError(Exception):
    pass


def list_files() -> list[dict]:
    response = requests.get(
        SCHEDULE_URL,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")
    table = soup.find("table", class_="schedule")
    if table is None:
        raise FetchError("Таблица расписания не найдена — похоже, изменилась вёрстка сайта")

    records = []
    for row in table.find_all("tr"):
        link = row.find("a")
        if not link or not link.get("href"):
            continue
        records.append({
            "filename": link["href"].split("/")[-1],
            "href": link["href"],
            "label": link.get("aria-label", "") or link.get_text(strip=True),
        })
    return records


def _match(records: list[dict]) -> dict:
    for pattern in COURSE_PATTERNS.get(COURSE, []):
        matched = [
            rec for rec in records
            if re.search(pattern, f'{rec["filename"]} {rec["label"]}', re.IGNORECASE)
        ]
        if len(matched) == 1:
            return matched[0]
        if matched:
            # несколько кандидатов — берём первый, но это стоит увидеть в логах
            logger.warning("Под курс %s подошло %d файлов, беру первый", COURSE, len(matched))
            return matched[0]
    raise FetchError(f"Файл расписания для курса {COURSE!r} на сайте не найден")


def _load_state() -> dict:
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state: dict) -> None:
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def fetch() -> tuple[str, bool]:
    """
    Скачивает актуальный файл расписания.
    Возвращает (путь к файлу, обновился ли он с прошлого запуска).
    """
    record = _match(list_files())

    response = requests.get(record["href"], timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    content = response.content

    digest = hashlib.sha256(content).hexdigest()
    state = _load_state()
    changed = state.get("sha256") != digest

    os.makedirs(SCHEDULE_DIR, exist_ok=True)
    path = os.path.join(SCHEDULE_DIR, record["filename"])
    with open(path, "wb") as f:
        f.write(content)

    _save_state({"sha256": digest, "filename": record["filename"], "href": record["href"]})
    return path, changed
