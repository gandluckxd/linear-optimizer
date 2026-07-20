# Headless runner для оптимизации москитных сеток

Runner принимает `GRORDERS_MOS.ID`, а не `ORDERID`: по этому ID API получает
связанные СЗ из `GRORDER_UF_VALUES` (`USERFIELDID = 8`). Он использует тот же
workflow, что и GUI: загрузка профилей/материалов, линейный и плоскостной
раскрой, запись карт, затем складские документы и номера ячеек.

## Конфигурация и запуск

Скопируйте `client/linear_optimizer_mos.example.txt` рядом с EXE как
`linear_optimizer_mos.txt`, укажите `api_url`, затем выполните:

```powershell
mos-optimizer-runner.exe 123 --dry-run
mos-optimizer-runner.exe 123
```

Безопасная проверка из исходников (не создаёт ни карт раскроя, ни складских
документов):

```powershell
cd client
py mos_optimizer_runner.py 123 --dry-run --config linear_optimizer_mos.txt
```

`--dry-run` загружает данные и запускает оба оптимизатора, но не вызывает ни
одного API-метода записи. В обоих режимах stdout содержит один JSON-объект с
итогом. Журнал и старые диагностические `print` выводятся только в stderr и в
`log_file` из конфигурации. В итоговом JSON есть количество деталей, карт и
отход, предупреждения, а также `documents.outlay_id` и `documents.supply_id`.

TXT открывается и редактируется обычным Блокнотом. Это плоский файл без
разделов: каждая настройка задаётся как `имя = значение`. Строки с `#` или `;`
в начале — комментарии; комментарий также можно поставить после значения.
Логические параметры принимают `да`/`нет`, `true`/`false` или `1`/`0`; дробные
числа можно писать через точку или запятую. Поддерживаются UTF-8, UTF-8 BOM и
Windows-1251 (ANSI). Ошибка указывает номер неправильной строки.

Чтобы использовать TXT-файл из другого места, передайте его явно:

```powershell
mos-optimizer-runner.exe 123 --config D:\Altawin\linear_optimizer_mos.txt
```

Коды завершения: `0` — успех, `2` — аргумент/конфиг, `3` — загрузка через API,
`4` — оптимизация, `5` — запись результатов/склад/ячейки, `10` — неожиданная
ошибка. При любой ошибке stdout также содержит JSON с `success: false`,
`stage`, `grorders_mos_id` и `error`.

## Складские документы и повторный запуск

При `adjust_materials: true` API создаёт непроведённые (`ISAPPROVED = 0`)
`OUTLAY` и `SUPPLY`. Списываются использованные целые хлысты и складские
остатки, а деловые остатки профиля и фибергласса приходятся в
`SUPPLYREMAINDER`; удалённые из СЗ материалы москиток переносятся из
`OUTLAYDETAIL_MOS_MATERIALS`.

Перед записью нового результата API удаляет предыдущие `OPTDETAIL_MOS` и
`OPTIMIZED_MOS` данного задания. Однако существующий GUI/API при каждом запуске
создаёт новые черновые `OUTLAY`/`SUPPLY`; runner намеренно сохраняет это
поведение. Повторный production-запуск допустим только после проверки номеров
документов из предыдущего JSON-итога.

## Сборка Windows EXE

Запускать на Windows, из корня репозитория:

```powershell
py -m pip install -r client\requirements-headless.txt
py -m PyInstaller --noconfirm --clean --distpath dist\windows --workpath build\windows linear-optimizer-headless.spec
Copy-Item client\linear_optimizer_mos.example.txt dist\windows\linear_optimizer_mos.txt
```

Результат: `dist\windows\mos-optimizer-runner.exe`. Рядом с ним должны лежать
`linear_optimizer_mos.txt`; папка `logs` создаётся автоматически. macOS-сборка не
может заменить Windows `.exe`.
