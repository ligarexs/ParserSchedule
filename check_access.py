"""
Диагностика подключения к Google Sheets.

Показывает: видит ли сервисный аккаунт таблицу вообще, и какие листы
в ней реально есть — по именам, посимвольно, чтобы отловить невидимые
пробелы или похожие буквы.

    python check_access.py
"""

import gspread
from google.oauth2.service_account import Credentials

from config import SERVICE_ACCOUNT_FILE, SPREADSHEET_ID, WORKSHEET_NAME

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def main():
    print(f"SPREADSHEET_ID = {SPREADSHEET_ID!r}")
    print(f"WORKSHEET_NAME = {WORKSHEET_NAME!r}\n")

    credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    print(f"Сервисный аккаунт: {credentials.service_account_email}")
    print("^ этот адрес должен быть добавлен в доступ таблицы как Редактор\n")

    client = gspread.authorize(credentials)

    try:
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
    except gspread.exceptions.SpreadsheetNotFound:
        print("ОШИБКА: таблица с таким SPREADSHEET_ID не найдена или нет доступа.")
        print("Проверьте: 1) id скопирован верно из ссылки между /d/ и /edit,")
        print("           2) email сервисного аккаунта добавлен в доступ таблицы.")
        return

    print(f"Таблица открыта: {spreadsheet.title!r}")
    print("Листы внутри:")
    for ws in spreadsheet.worksheets():
        match = "  <-- совпадает с WORKSHEET_NAME" if ws.title == WORKSHEET_NAME else ""
        print(f"  {ws.title!r}{match}")

    if WORKSHEET_NAME not in [ws.title for ws in spreadsheet.worksheets()]:
        print(f"\nОШИБКА: листа {WORKSHEET_NAME!r} нет среди перечисленных выше.")
        print("Исправьте WORKSHEET_NAME в config.py на точное имя из списка.")
    else:
        print("\nВсё в порядке, лист найден.")


if __name__ == "__main__":
    main()
