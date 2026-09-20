"""
    Превращает список Lesson в сетку будущей гугл-таблицы.

    Модуль намеренно ничего не знает про Google API: он строит абстрактную
    сетку (значения, объединения, цвета, где начинается серый "хвост" с
    аудиторией). Благодаря этому вёрстку можно проверить локально, не трогая
    таблицу и не имея доступа к сети — см. preview.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from config import (
    COLOR_EMPTY,
    COLOR_LECTURE,
    COLOR_ONLINE,
    COLOR_SEMINAR,
    MIN_ROWS_PER_DAY,
    SUBGROUP_COUNT,
    SUBJECT_OVERRIDES,
    WEEK_DAYS,
)
from parser import KIND_LECTURE, KIND_SEMINAR, Lesson

DAY_TITLES = {"ПН": "ПН", "ВТ": "ВТ", "СР": "СР", "ЧТ": "ЧТ", "ПТ": "ПТ"}

COLOR_TIME_FIRST = (0.80, 0.25, 0.20)   # красное время первой пары дня
COLOR_TEXT = (0.10, 0.10, 0.10)
COLOR_DETAIL = (0.45, 0.45, 0.45)       # серый хвост ", ауд. 505"


@dataclass
class Cell:
    text: str = ""
    bg: tuple[float, float, float] = COLOR_EMPTY
    bold: bool = False
    text_color: tuple[float, float, float] = COLOR_TEXT
    detail_at: int | None = None        # индекс, с которого текст становится серым
    italic: bool = False
    size: int = 10


@dataclass
class Grid:
    rows: list[list[Cell]] = field(default_factory=list)
    merges: list[tuple[int, int, int, int]] = field(default_factory=list)
    width: int = 4                      # Время | 1-я подгруппа | 2-я подгруппа | Д/Н

    def add_row(self, cells: list[Cell]) -> int:
        while len(cells) < self.width:
            cells.append(Cell())
        self.rows.append(cells)
        return len(self.rows) - 1


def _background(lesson: Lesson) -> tuple[float, float, float]:
    if lesson.online and lesson.kind == KIND_LECTURE:
        return COLOR_ONLINE
    if lesson.kind == KIND_LECTURE:
        return COLOR_LECTURE
    if lesson.kind == KIND_SEMINAR:
        return COLOR_SEMINAR
    return COLOR_EMPTY


def _lesson_cell(lesson: Lesson) -> Cell:
    place = lesson.place()
    text = f"{lesson.subject}, {place}" if place else lesson.subject
    return Cell(
        text=text,
        bg=_background(lesson),
        bold=True,
        detail_at=len(lesson.subject) if place else None,
    )


def _slot_map(lessons: list[Lesson], day: str) -> dict[str, list[Lesson]]:
    slots: dict[str, list[Lesson]] = {}
    for lesson in lessons:
        if lesson.day == day:
            slots.setdefault(lesson.time, []).append(lesson)
    return dict(sorted(slots.items(), key=lambda kv: _time_key(kv[0])))


def _time_key(time: str) -> tuple[int, int]:
    hour, minute = time.split(":")
    return int(hour), int(minute)


def build_grid(lessons: list[Lesson], week_label: str = "") -> Grid:
    grid = Grid()

    title = f"Расписание ({week_label})" if week_label else "Расписание"
    row = grid.add_row([Cell(text=title, bold=True)])
    grid.merges.append((row, 0, row, 3))

    grid.add_row([
        Cell(text="Время", bold=True),
        Cell(text="Первая подгруппа", bold=True),
        Cell(text="Вторая подгруппа", bold=True),
        Cell(text="Д/Н", bold=True),
    ])

    for day in WEEK_DAYS:
        slots = _slot_map(lessons, day)
        times = list(slots.keys())
        row_count = max(MIN_ROWS_PER_DAY, len(times))
        first_row = len(grid.rows)

        for index in range(row_count):
            if index < len(times):
                time = times[index]
                day_lessons = slots[time]
                time_cell = Cell(
                    text=time,
                    bold=True,
                    text_color=COLOR_TIME_FIRST if index == 0 else COLOR_TEXT,
                )
                cells = [time_cell, Cell(), Cell(), Cell()]

                whole = [l for l in day_lessons if l.whole_group]
                if whole:
                    cells[1] = _lesson_cell(whole[0])
                    cells[2] = Cell(bg=cells[1].bg)
                    row_index = grid.add_row(cells)
                    grid.merges.append((row_index, 1, row_index, 2))
                    continue

                for lesson in day_lessons:
                    for subgroup in lesson.subgroups:
                        if 1 <= subgroup <= SUBGROUP_COUNT:
                            cells[subgroup] = _lesson_cell(lesson)
                grid.add_row(cells)
            else:
                grid.add_row([Cell(), Cell(), Cell(), Cell()])

        last_row = len(grid.rows) - 1
        grid.rows[first_row][3] = Cell(text=DAY_TITLES.get(day, day), bold=True)
        if last_row > first_row:
            grid.merges.append((first_row, 3, last_row, 3))

    # Сноски из ручных уточнений
    for short, override in SUBJECT_OVERRIDES.items():
        note = override.get("note")
        if note and any(l.subject == short for l in lessons):
            row_index = grid.add_row([Cell(), Cell(text=note, italic=True, size=9)])
            grid.merges.append((row_index, 1, row_index, 2))

    # Легенда
    grid.add_row([
        Cell(),
        Cell(text="● — лекции", bg=COLOR_LECTURE, size=9),
        Cell(text="● — семинары", bg=COLOR_SEMINAR, size=9),
    ])
    grid.add_row([
        Cell(),
        Cell(text="● — онлайн-лекции", bg=COLOR_ONLINE, size=9),
    ])

    return grid
