"""
Разбор xlsx-расписания ESIL University в структуры Lesson.

Ключевые решения (почему именно так — см. разбор сырого файла):

1. Лист ищется по наличию нужной группы в строке-шапке, а не по имени
   листа. Университет переименовывает листы ("ФПН рус" / "ФПН каз"),
   но название группы стабильно.

2. Лист режется по блокам дней (объединённые ячейки в колонке A).
   Ниже блока подписей "Согласовано / Диспетчер" в файле лежат обрывки
   пар без дня и времени — остатки правок диспетчера. Они ОБЯЗАНЫ быть
   отрезаны, иначе однажды попадут в таблицу.

3. Номер подгруппы берётся из маркера "семинар 2/2" внутри текста, а не
   из позиции колонки. В исходном файле колонки подгрупп идут в
   произвольном порядке: в среду 14:00 в первой колонке лежит пара
   второй подгруппы. Позиционный разбор регулярно менял бы подгруппы
   местами.

4. Пара, записанная в объединённую ячейку на все колонки группы
   (или с маркером 1/1), считается парой всей группы.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import openpyxl

from config import SUBGROUP_COUNT, SUBJECT_OVERRIDES, SUBJECT_SHORT_NAMES

# Дни: русские и казахские написания -> (код, порядковый номер)
DAY_ALIASES = {
    "понедельник": ("ПН", 0), "дүйсенбі": ("ПН", 0),
    "вторник": ("ВТ", 1), "сейсенбі": ("ВТ", 1),
    "среда": ("СР", 2), "сәрсенбі": ("СР", 2),
    "четверг": ("ЧТ", 3), "бейсенбі": ("ЧТ", 3),
    "пятница": ("ПТ", 4), "жұма": ("ПТ", 4),
    "суббота": ("СБ", 5), "сенбі": ("СБ", 5),
}

HEADER_MARKERS = {"дни", "күні", "кун"}

KIND_LECTURE = "lecture"
KIND_SEMINAR = "seminar"
KIND_OTHER = "other"

RE_SUBGROUP = re.compile(r"(?<!\d)(\d)\s*/\s*(\d)(?!\d)")
RE_ROOM = re.compile(r"ауд\.?\s*№?\s*(\d+(?:\s*[,/]\s*\d+)*)", re.IGNORECASE)
RE_TIME = re.compile(r"(\d{1,2})[.:](\d{2})")
RE_ONLINE = re.compile(r"онлайн|online", re.IGNORECASE)


class ParseError(Exception):
    pass


@dataclass
class Lesson:
    day: str                 # 'СР'
    day_index: int           # 2
    time: str                # '14:00'
    subject: str             # короткое имя для таблицы
    subject_raw: str         # полное имя из файла
    kind: str                # lecture / seminar / other
    online: bool
    room: str | None
    teacher: str
    subgroups: tuple[int, ...] = field(default_factory=tuple)
    raw: str = ""

    @property
    def whole_group(self) -> bool:
        return len(self.subgroups) >= SUBGROUP_COUNT

    def place(self) -> str:
        if self.online:
            return "онлайн"
        return f"ауд. {self.room}" if self.room else ""


# --- вспомогательное -------------------------------------------------------

def _clean(value) -> str:
    if value is None:
        return ""
    text = str(value)
    text = text.replace("\n", " ").replace("\r", " ")
    text = text.replace("\xa0", " ").replace("\u202f", " ")
    return re.sub(r"\s+", " ", text).strip()


def _merge_index(sheet) -> dict[tuple[int, int], tuple[int, int, int, int]]:
    """(row, col) -> границы объединённого диапазона, которому она принадлежит."""
    index = {}
    for rng in sheet.merged_cells.ranges:
        bounds = (rng.min_row, rng.min_col, rng.max_row, rng.max_col)
        for r in range(rng.min_row, rng.max_row + 1):
            for c in range(rng.min_col, rng.max_col + 1):
                index[(r, c)] = bounds
    return index


def _value(sheet, merges, row: int, col: int) -> str:
    """Значение ячейки с учётом объединений (берём из левой верхней)."""
    cell = sheet.cell(row, col)
    if cell.value is not None:
        return _clean(cell.value)
    bounds = merges.get((row, col))
    if bounds:
        return _clean(sheet.cell(bounds[0], bounds[1]).value)
    return ""


def _normalize_time(text: str) -> str | None:
    """'14.00-14.50' -> '14:00'."""
    match = RE_TIME.search(text)
    if not match:
        return None
    return f"{int(match.group(1))}:{match.group(2)}"


def _short_name(full: str) -> str:
    lowered = full.lower()
    for needle, short in SUBJECT_SHORT_NAMES.items():
        if needle in lowered:
            return short
    return full


def _detect_kind(text: str) -> str:
    lowered = text.lower()
    if re.search(r"\bлекц|\bлек\b", lowered):
        return KIND_LECTURE
    if re.search(r"\bсеминар|\bсем\b|практ", lowered):
        return KIND_SEMINAR
    return KIND_OTHER


def parse_cell(text: str) -> dict | None:
    """Разбирает текст одной ячейки пары на составляющие."""
    text = _clean(text)
    if not text or len(text) < 4:
        return None

    parts = [p.strip() for p in text.split(",")]
    subject_raw = parts[0]
    rest = parts[1:]

    room_match = RE_ROOM.search(text)
    room = None
    if room_match:
        # "308,309,311,312" -> "308/309/311/312"
        room = "/".join(p.strip() for p in re.split(r"[,/]", room_match.group(1)) if p.strip())

    subgroup_match = RE_SUBGROUP.search(text)
    subgroup_no = int(subgroup_match.group(1)) if subgroup_match else None
    subgroup_total = int(subgroup_match.group(2)) if subgroup_match else None

    # преподаватель — всё, что осталось после вычистки служебных кусков
    teacher_parts = []
    for part in rest:
        lowered = part.lower()
        if RE_ROOM.search(part) or RE_ONLINE.search(part):
            continue
        if re.fullmatch(r"(лекция|лек|семинар|сем|практика)\s*\d*\s*/?\s*\d*", lowered):
            continue
        teacher_parts.append(part)

    short = _short_name(subject_raw)

    # Ручные уточнения: университет иногда пишет все аудитории потока
    # одной строкой ("ауд. 308,309,311,312" на четырёх преподавателей),
    # и автоматически понять, какие из них ваши, невозможно.
    override = SUBJECT_OVERRIDES.get(short)
    if override and override.get("room"):
        room = override["room"]

    return {
        "subject_raw": subject_raw,
        "subject": short,
        "kind": _detect_kind(text),
        "online": bool(RE_ONLINE.search(text)),
        "room": room,
        "teacher": ", ".join(teacher_parts).strip(),
        "subgroup_no": subgroup_no,
        "subgroup_total": subgroup_total,
        "raw": text,
    }


# --- разбор листа ----------------------------------------------------------

def _find_sheet(workbook, group: str):
    """Ищет лист, в шапке которого встречается нужная группа."""
    for name in workbook.sheetnames:
        sheet = workbook[name]
        for row in sheet.iter_rows(min_row=1, max_row=min(20, sheet.max_row)):
            for cell in row:
                if _clean(cell.value) == group:
                    return sheet, cell.row, cell.column
    raise ParseError(f"Группа {group!r} не найдена ни на одном листе файла")


def _group_columns(sheet, merges, header_row: int, header_col: int) -> list[int]:
    """Колонки, которые занимает группа (шапка обычно объединена K13:L13)."""
    bounds = merges.get((header_row, header_col))
    if bounds:
        return list(range(bounds[1], bounds[3] + 1))
    return [header_col]


def _day_blocks(sheet, merges, header_row: int) -> list[tuple[str, int, int, int]]:
    """
    Возвращает [(код дня, индекс дня, первая строка, последняя строка)].
    Останавливается на первой строке, где в колонке A нет известного дня —
    это отрезает блок подписей и мусор под ним.
    """
    blocks = []
    row = header_row + 1
    while row <= sheet.max_row:
        raw_day = _value(sheet, merges, row, 1).lower().strip()
        if raw_day not in DAY_ALIASES:
            row += 1
            # день не найден: если блоки уже были — дальше идёт подвал файла
            if blocks and row - blocks[-1][3] > 3:
                break
            continue
        code, index = DAY_ALIASES[raw_day]
        bounds = merges.get((row, 1))
        first, last = (bounds[0], bounds[2]) if bounds else (row, row)
        blocks.append((code, index, first, last))
        row = last + 1
    return blocks


def parse_file(file_path: str, group: str) -> tuple[list[Lesson], list[str]]:
    """
    Возвращает (список пар, список дней, которые этот файл покрывает).

    Второе значение важно: университет публикует файлы не на всю неделю —
    в разобранном образце были только Ср/Чт/Пт. Писать в таблицу можно
    только те дни, которые файл реально покрывает, иначе остальные дни
    будут затёрты пустотой.
    """
    workbook = openpyxl.load_workbook(file_path, data_only=True)
    try:
        sheet, header_row, header_col = _find_sheet(workbook, group)
        merges = _merge_index(sheet)
        columns = _group_columns(sheet, merges, header_row, header_col)
        blocks = _day_blocks(sheet, merges, header_row)

        lessons: list[Lesson] = []
        covered_days: list[str] = []

        for code, day_index, first, last in blocks:
            covered_days.append(code)
            for row in range(first, last + 1):
                time = _normalize_time(_value(sheet, merges, row, 2))
                if not time:
                    continue

                # Собираем пары по колонкам группы, схлопывая объединения
                seen_ranges = set()
                found: list[tuple[dict, tuple[int, int, int, int] | None, int]] = []
                for col in columns:
                    bounds = merges.get((row, col))
                    key = bounds or (row, col, row, col)
                    if key in seen_ranges:
                        continue
                    seen_ranges.add(key)
                    parsed = parse_cell(_value(sheet, merges, row, col))
                    if parsed:
                        found.append((parsed, bounds, col))

                for parsed, bounds, col in found:
                    lessons.append(
                        Lesson(
                            day=code,
                            day_index=day_index,
                            time=time,
                            subject=parsed["subject"],
                            subject_raw=parsed["subject_raw"],
                            kind=parsed["kind"],
                            online=parsed["online"],
                            room=parsed["room"],
                            teacher=parsed["teacher"],
                            subgroups=_resolve_subgroups(parsed, bounds, columns, found),
                            raw=parsed["raw"],
                        )
                    )

        lessons.sort(key=lambda l: (l.day_index, _time_key(l.time), l.subgroups))
        return lessons, covered_days
    finally:
        workbook.close()


def _time_key(time: str) -> tuple[int, int]:
    hour, minute = time.split(":")
    return int(hour), int(minute)


def _resolve_subgroups(parsed, bounds, columns, found) -> tuple[int, ...]:
    """
    Определяет, каким подгруппам принадлежит пара.

    Приоритет:
    1. Маркер вида "2/2" в тексте — самый надёжный источник.
    2. Ячейка объединена на все колонки группы -> вся группа.
    3. Пара единственная в строке -> вся группа.
    4. Иначе — по позиции колонки (запасной вариант).
    """
    total = parsed["subgroup_total"]
    number = parsed["subgroup_no"]

    if number and total:
        if total == 1 or number > SUBGROUP_COUNT:
            return tuple(range(1, SUBGROUP_COUNT + 1))
        return (number,)

    if bounds and bounds[3] - bounds[1] + 1 >= len(columns):
        return tuple(range(1, SUBGROUP_COUNT + 1))

    if len(found) == 1:
        return tuple(range(1, SUBGROUP_COUNT + 1))

    position = columns.index(found[[f[0] for f in found].index(parsed)][2]) + 1
    return (min(position, SUBGROUP_COUNT),)
