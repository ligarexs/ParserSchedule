"""
Запись сетки в Google Sheets одним batch-запросом.

Почему целиком, а не точечно: расписание меняется непредсказуемо (пара
исчезла, сдвинулась, поменялась аудитория). Диффать такое — источник
вечных расхождений. Полная перерисовка блока делает состояние таблицы
однозначной функцией от исходного файла.

Что при этом НЕ затирается: всё, что лежит за пределами блока
расписания. Ручные заметки держите ниже легенды или на соседнем листе.
"""

from __future__ import annotations

import gspread
from google.oauth2.service_account import Credentials

from config import (
    ANCHOR_COL,
    ANCHOR_ROW,
    CLEAR_ROWS,
    FONT_FAMILY,
    SERVICE_ACCOUNT_FILE,
    SPREADSHEET_ID,
    WORKSHEET_NAME,
)
from renderer import Cell, Grid

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _color(rgb: tuple[float, float, float]) -> dict:
    red, green, blue = rgb
    return {"red": red, "green": green, "blue": blue}


def _text_format(cell: Cell, bold: bool | None = None, color=None) -> dict:
    return {
        "bold": cell.bold if bold is None else bold,
        "italic": cell.italic,
        "fontSize": cell.size,
        "fontFamily": FONT_FAMILY,
        "foregroundColor": _color(color or cell.text_color),
    }


def _cell_data(cell: Cell) -> dict:
    data = {
        "userEnteredValue": {"stringValue": cell.text} if cell.text else {},
        "userEnteredFormat": {
            "backgroundColor": _color(cell.bg),
            "horizontalAlignment": "CENTER",
            "verticalAlignment": "MIDDLE",
            "wrapStrategy": "CLIP",
            "textFormat": _text_format(cell),
        },
    }
    # Хвост ", ауд. 505" — мельче и серым, как в текущей таблице
    if cell.detail_at is not None and cell.text:
        data["textFormatRuns"] = [
            {"startIndex": 0, "format": _text_format(cell)},
            {
                "startIndex": cell.detail_at,
                "format": _text_format(cell, bold=False, color=(0.45, 0.45, 0.45)),
            },
        ]
    return data


def _connect():
    credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    client = gspread.authorize(credentials)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    return spreadsheet, spreadsheet.worksheet(WORKSHEET_NAME)


def write_grid(grid: Grid) -> None:
    spreadsheet, worksheet = _connect()
    sheet_id = worksheet.id

    start_row = ANCHOR_ROW - 1          # API считает от нуля
    start_col = ANCHOR_COL - 1
    end_row = start_row + max(len(grid.rows), CLEAR_ROWS)
    end_col = start_col + grid.width

    block = {
        "sheetId": sheet_id,
        "startRowIndex": start_row,
        "endRowIndex": end_row,
        "startColumnIndex": start_col,
        "endColumnIndex": end_col,
    }

    requests: list[dict] = [
        # 1. Снимаем старые объединения — иначе новые лягут поверх конфликтом
        {"unmergeCells": {"range": block}},
        # 2. Чистим весь блок, включая строки ниже нового расписания
        {
            "updateCells": {
                "range": block,
                "fields": "userEnteredValue,userEnteredFormat,textFormatRuns",
            }
        },
        # 3. Пишем новую сетку
        {
            "updateCells": {
                "start": {
                    "sheetId": sheet_id,
                    "rowIndex": start_row,
                    "columnIndex": start_col,
                },
                "rows": [
                    {"values": [_cell_data(cell) for cell in row]}
                    for row in grid.rows
                ],
                "fields": "userEnteredValue,userEnteredFormat,textFormatRuns",
            }
        },
    ]

    for r1, c1, r2, c2 in grid.merges:
        requests.append({
            "mergeCells": {
                "mergeType": "MERGE_ALL",
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": start_row + r1,
                    "endRowIndex": start_row + r2 + 1,
                    "startColumnIndex": start_col + c1,
                    "endColumnIndex": start_col + c2 + 1,
                },
            }
        })

    # 4. Рамки по блоку расписания
    border = {"style": "SOLID", "width": 1, "color": _color((0.4, 0.4, 0.4))}
    requests.append({
        "updateBorders": {
            "range": {**block, "endRowIndex": start_row + len(grid.rows)},
            "top": border,
            "bottom": border,
            "left": border,
            "right": border,
            "innerHorizontal": {**border, "color": _color((0.75, 0.75, 0.75))},
            "innerVertical": {**border, "color": _color((0.75, 0.75, 0.75))},
        }
    })

    spreadsheet.batch_update({"requests": requests})
