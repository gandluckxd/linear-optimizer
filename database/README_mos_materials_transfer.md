# Система переноса материалов москитных сеток

## Описание

Реализована система автоматического переноса материалов москитных сеток из списаний СЗ конструкций в списание СЗ москитных сеток через триггеры и сводную таблицу.

## Архитектура решения

### 1. Сводная таблица `OUTLAYDETAIL_MOS_MATERIALS`

Хранит информацию о материалах москиток, которые были удалены из списаний СЗ конструкций триггером `DELETE_MOS_STUFFS`.

**Структура:**
- `ID` - первичный ключ
- `OUTLAYID` - ID списания
- `OUTLAYDETAILID` - ID удаленной записи из OUTLAYDETAIL
- `GOODSID` - ID материала
- `QTY` - количество
- `MEASUREID` - ID единицы измерения
- `GRORDERID` - ID сменного задания конструкций
- `GGTYPEID` - ID типа группы материала
- `DATECREATED` - дата создания записи

### 2. Триггер `SAVE_MOS_MATERIALS_BD`

**Тип:** BEFORE DELETE на таблице OUTLAYDETAIL
**Позиция:** 0 (выполняется ПЕРЕД DELETE_MOS_STUFFS)

**Логика:**
1. При удалении записи из OUTLAYDETAIL проверяет:
   - Относится ли списание к СЗ конструкций (OUTLAY.GRORDERID IS NOT NULL)
   - Является ли материал москиткой (CODE IN ('MosNetShnur', 'MosNetShip', 'MosNet'))
2. Если оба условия выполнены - сохраняет запись в OUTLAYDETAIL_MOS_MATERIALS
3. После этого срабатывает DELETE_MOS_STUFFS и удаляет материал

### 3. Триггер `CLEAN_MOS_MAT_ON_OUTLAY_DELETE`

**Тип:** AFTER UPDATE на таблице OUTLAY
**Позиция:** 0

**Логика:**
- При пометке списания на удаление (DELETED = 0 → 1) удаляет связанные записи из OUTLAYDETAIL_MOS_MATERIALS
- Также работает каскадное удаление через FK_ODMOS_OUTLAY при физическом удалении OUTLAY

### 4. Python функция `transfer_moskitka_materials_from_grorders()`

**Расположение:** `api/utils/db_functions.py:1629`

**Логика:**
1. Получает все GRORDERID связанные с СЗ москитных сеток
2. Читает материалы из сводной таблицы OUTLAYDETAIL_MOS_MATERIALS
3. Группирует по GOODSID + MEASUREID и суммирует QTY
4. Возвращает список для добавления в новое списание
5. НЕ удаляет записи из сводной таблицы (удаление происходит позже)

### 5. Интеграция в `adjust_materials_for_moskitka_optimization()`

**Расположение:** `api/utils/db_functions.py:1361`

**Процесс:**
1. Вызывает `transfer_moskitka_materials_from_grorders()` для получения материалов
2. Добавляет полученные материалы в новое списание OUTLAY
3. ПОСЛЕ успешного добавления очищает сводную таблицу (удаляет записи для данных GRORDERID)

## Типы материалов москиток

- **MosNetShnur** (GGTYPEID: 62) - Шнур для москитных сеток
- **MosNetShip** (GGTYPEID: 54) - Комплектующие на отгрузку
- **MosNet** (GGTYPEID: 35) - Профили москитных сеток

## Установка

### Шаг 1: Таблица создана автоматически

Таблица `OUTLAYDETAIL_MOS_MATERIALS` уже создана через MCP Firebird вместе с индексами.

### Шаг 2: Создание триггеров

Выполните SQL-скрипт `create_mos_materials_triggers.sql` через FlameRobin, IBExpert или другой клиент Firebird:

```bash
isql -user SYSDBA -password masterkey localhost:C:\path\to\database.fdb -i create_mos_materials_triggers.sql
```

Или вручную через GUI клиент.

### Шаг 3: Проверка установки

```sql
-- Проверка наличия триггеров
SELECT RDB$TRIGGER_NAME, RDB$TRIGGER_TYPE, RDB$TRIGGER_SEQUENCE
FROM RDB$TRIGGERS
WHERE RDB$RELATION_NAME = 'OUTLAYDETAIL'
    AND RDB$SYSTEM_FLAG = 0
ORDER BY RDB$TRIGGER_TYPE, RDB$TRIGGER_SEQUENCE;

-- Должны быть:
-- SAVE_MOS_MATERIALS_BD (TRIGGER_TYPE=5, SEQUENCE=0) - BEFORE DELETE
-- DELETE_MOS_STUFFS (TRIGGER_TYPE=2, SEQUENCE=1) - AFTER INSERT

-- Проверка таблицы
SELECT COUNT(*) FROM OUTLAYDETAIL_MOS_MATERIALS;
```

## Workflow (Поток работы)

```
1. Оператор создает списание материалов к СЗ конструкций в Altawin
   ↓
2. В списании есть материалы москиток (MosNetShnur, MosNetShip, MosNet)
   ↓
3. Триггер DELETE_MOS_STUFFS удаляет эти материалы из OUTLAYDETAIL
   ↓
4. НО! Триггер SAVE_MOS_MATERIALS_BD срабатывает ПЕРЕД DELETE_MOS_STUFFS
   и сохраняет материалы в OUTLAYDETAIL_MOS_MATERIALS
   ↓
5. Материалы удалены из списания, но сохранены в сводной таблице
   ↓
6. Оператор запускает оптимизацию москитных сеток в приложении
   ↓
7. При нажатии "Загрузить данные в Altawin" с галочкой "Скорректировать материалы"
   ↓
8. Python функция transfer_moskitka_materials_from_grorders()
   читает материалы из OUTLAYDETAIL_MOS_MATERIALS
   ↓
9. Материалы группируются и добавляются в новое списание к СЗ москитных сеток
   ↓
10. После успешного добавления сводная таблица очищается
```

## Преимущества решения

✅ **Не трогает проведенные списания** - старые списания СЗ конструкций не изменяются
✅ **Автоматическое сохранение** - триггеры работают прозрачно для пользователя
✅ **Надежность** - материалы не теряются, всегда есть в сводной таблице
✅ **Очистка** - автоматическое удаление при удалении OUTLAY или после успешного переноса
✅ **Производительность** - индексы по OUTLAYID, GRORDERID, GGTYPEID

## Тестирование

### Тест 1: Проверка сохранения материалов

```sql
-- 1. Создайте тестовое списание к СЗ конструкций с материалом москитки
-- 2. Триггер DELETE_MOS_STUFFS удалит материал
-- 3. Проверьте, что материал сохранился в сводной таблице:

SELECT * FROM OUTLAYDETAIL_MOS_MATERIALS
WHERE GRORDERID = <ваш_grorderid>
ORDER BY DATECREATED DESC;
```

### Тест 2: Проверка переноса

```python
# В Python через API клиент
result = api_client.adjust_materials_altawin(
    grorders_mos_id=<ваш_id>,
    used_materials=[...],
    business_remainders=[...]
)

print(f"Перенесено: {result['transferred_materials_count']} типов")
print(f"Записей: {result['transferred_records_count']}")
```

### Тест 3: Проверка очистки

```sql
-- После успешного переноса сводная таблица должна быть пустой для данных GRORDERID:

SELECT COUNT(*) FROM OUTLAYDETAIL_MOS_MATERIALS
WHERE GRORDERID IN (
    SELECT GRORDERID FROM GRORDER_UF_VALUES
    WHERE USERFIELDID = 8 AND VAR_STR = '<ваш_grorders_mos_id>'
);

-- Должно быть 0
```

## Troubleshooting

### Материалы не сохраняются в сводную таблицу

Проверьте:
1. Триггер SAVE_MOS_MATERIALS_BD создан и активен
2. Позиция триггера = 0 (выполняется перед DELETE_MOS_STUFFS)
3. Материал относится к типам MosNetShnur, MosNetShip или MosNet

### Материалы не переносятся

Проверьте:
1. Есть ли записи в OUTLAYDETAIL_MOS_MATERIALS для данных GRORDERID
2. Правильно ли заполнено GRORDER_UF_VALUES (USERFIELDID = 8)
3. Логи Python приложения на наличие ошибок

### Сводная таблица растет

Проверьте:
1. Триггер CLEAN_MOS_MAT_ON_OUTLAY_DELETE создан и активен
2. Каскадное удаление работает (FK_ODMOS_OUTLAY)
3. Python код очищает таблицу после переноса

## Контакты

При возникновении проблем проверьте логи:
- Python: консоль приложения
- Firebird: firebird.log

---
**Дата создания:** 2025-12-01
**Версия:** 1.0
**Автор:** Claude Code
