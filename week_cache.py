"""
Кэш недели.

Зачем: университет публикует файлы не на всю неделю — разобранный образец
покрывал только Ср/Чт/Пт. Если писать в таблицу голый результат парсинга,
понедельник и вторник будут затёрты пустотой при каждой выгрузке.

Решение: локальный JSON хранит расписание всей недели. Новый файл
перезаписывает только те дни, которые он покрывает; остальные остаются
от прошлой выгрузки.

Дни, перечисленные в config.MANUAL_DAYS, не трогаются парсером никогда —
их можно вести вручную в manual_week.json, пока не станет понятно,
откуда университет отдаёт начало недели.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict

from config import MANUAL_DAYS
from parser import Lesson

CACHE_PATH = "week_cache.json"
MANUAL_PATH = "manual_week.json"


def _to_dict(lesson: Lesson) -> dict:
    data = asdict(lesson)
    data["subgroups"] = list(lesson.subgroups)
    return data


def _from_dict(data: dict) -> Lesson:
    data = dict(data)
    data["subgroups"] = tuple(data.get("subgroups", ()))
    allowed = Lesson.__dataclass_fields__.keys()
    return Lesson(**{k: v for k, v in data.items() if k in allowed})


def _load(path: str) -> list[Lesson]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return [_from_dict(item) for item in json.load(f)]
    except (json.JSONDecodeError, TypeError, OSError):
        return []


def load_cache() -> list[Lesson]:
    return _load(CACHE_PATH)


def load_manual() -> list[Lesson]:
    return _load(MANUAL_PATH)


def save_cache(lessons: list[Lesson]) -> None:
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump([_to_dict(l) for l in lessons], f, ensure_ascii=False, indent=2)


def merge_week(fresh: list[Lesson], covered_days: list[str]) -> list[Lesson]:
    """
    Склеивает свежий разбор с кэшем и ручными днями.
    Приоритет: ручные дни > свежий файл > кэш.
    """
    manual = load_manual()
    manual_days = set(MANUAL_DAYS) | {l.day for l in manual}
    fresh_days = set(covered_days) - manual_days

    result = [l for l in manual]
    result += [l for l in fresh if l.day in fresh_days]

    kept_days = manual_days | fresh_days
    result += [l for l in load_cache() if l.day not in kept_days]

    result.sort(key=lambda l: (l.day_index, _time_key(l.time), l.subgroups))
    return result


def _time_key(time: str) -> tuple[int, int]:
    hour, minute = time.split(":")
    return int(hour), int(minute)
