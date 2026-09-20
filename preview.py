"""
    Локальный просмотр будущей таблицы
    без сети и без доступа к Google
"""

import sys

from config import GROUP, WEEK_LABEL
from parser import parse_file
from renderer import build_grid

SYMBOL = {
    (0.85, 0.92, 0.83): "лек",
    (1.0, 0.95, 0.8): "сем",
    (0.81, 0.87, 0.95): "онл",
}

def main(path):
    lessons, days = parse_file(path, GROUP)
    print("Дни из файла:", ", ".join(days), "\n")
    grid = build_grid(lessons, WEEK_LABEL)
    merged = {(r1, c1): (r2, c2) for r1, c1, r2, c2 in grid.merges}
    for r, row in enumerate(grid.rows):
        out = []
        for c, cell in enumerate(row):
            tag = SYMBOL.get(tuple(round(x, 2) for x in cell.bg), "")
            text = cell.text
            if (r, c) in merged and merged[(r, c)][1] > c:
                text += " →"
            out.append(f"{text:<38}{('['+tag+']') if tag else '     '}")
        print(f"{r:>2} | " + "| ".join(out))

if __name__ == "__main__":
    main(sys.argv[1])
