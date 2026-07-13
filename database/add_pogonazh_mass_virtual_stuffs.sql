/*
  Создание расчетных артикулов массы для погонажных наборов с прибавками.

  Логика:
  - Создает новый STUFFTYPES: Погонаж / Pogonazh.
  - Создает STUFFS с массой в граммах на кв.м (MEASUREID = 8).
  - Добавляет STUFFSETS_ITEMS только в активные наборы с прибавками из скрина:
    Коробка, Подоконник, Наличник, Откос, Фальш коробка, Направляющий брусок.
  - Формулы количества копируются из существующих основных древесных строк наборов.
*/

INSERT INTO STUFFTYPES (
  ID, NAME, CODE, POSIT, ISADD, OWNERID, GUID, DELETED,
  DATECREATED, DATEMODIFIED
)
SELECT
  GEN_ID(GEN_STUFFTYPES, 1),
  'Погонаж',
  'Pogonazh',
  (SELECT COALESCE(MAX(POSIT), 0) + 1 FROM STUFFTYPES),
  0,
  0,
  CAST('{' || TRIM(UUID_TO_CHAR(GEN_UUID())) || '}' AS CHAR(38)),
  0,
  CURRENT_TIMESTAMP,
  CURRENT_TIMESTAMP
FROM RDB$DATABASE
WHERE NOT EXISTS (
  SELECT 1
  FROM STUFFTYPES
  WHERE (NAME = 'Погонаж' OR CODE = 'Pogonazh')
    AND COALESCE(DELETED, 0) = 0
);

INSERT INTO STUFFS (
  ID, STUFFTYPEID, NAME, MARKING, CURRENCYID, PRICE1, PRICE2,
  PURCHASEPOLICY, ALLOWSALE, DENYDEALERSALE, ALLOWDEALERSAVE,
  MEASUREID, WEIGHT, WASTE, DIRECTEDPATTERN, USEWAREHOUSE,
  LASTEDITORID, RCOMMENT, ISADD, OWNERID, GUID, DELETED,
  DATECREATED, DATEMODIFIED, USEWASTE, BENDABLE, ISKITPART,
  COATINGTYPE, FULLCOATING, TYPE, WASTEPOLICY, USECOATINGGROUP,
  FOLDDYEING
)
SELECT
  GEN_ID(GEN_STUFFS, 1),
  (SELECT FIRST 1 ID
   FROM STUFFTYPES
   WHERE (NAME = 'Погонаж' OR CODE = 'Pogonazh')
     AND COALESCE(DELETED, 0) = 0
   ORDER BY ID),
  d.NAME,
  NULL,
  1,
  NULL,
  NULL,
  0,
  0,
  0,
  0,
  8,
  d.WEIGHT,
  NULL,
  0,
  0,
  0,
  'расчетная масса погонажа',
  NULL,
  0,
  CAST('{' || TRIM(UUID_TO_CHAR(GEN_UUID())) || '}' AS CHAR(38)),
  0,
  CURRENT_TIMESTAMP,
  CURRENT_TIMESTAMP,
  0,
  0,
  0,
  0,
  0,
  0,
  0,
  0,
  0
FROM (
  SELECT CAST('Коробка сосна 40мм' AS VARCHAR(128)) AS NAME, CAST(20000 AS DOUBLE PRECISION) AS WEIGHT FROM RDB$DATABASE
  UNION ALL SELECT 'Коробка лиственница 40мм', 30000 FROM RDB$DATABASE
  UNION ALL SELECT 'Коробка дуб 40мм', 35000 FROM RDB$DATABASE
  UNION ALL SELECT 'Коробка осина 40мм', 20000 FROM RDB$DATABASE
  UNION ALL SELECT 'Подоконник сосна 40мм', 20000 FROM RDB$DATABASE
  UNION ALL SELECT 'Подоконник лиственница 40мм', 30000 FROM RDB$DATABASE
  UNION ALL SELECT 'Подоконник дуб 40мм', 35000 FROM RDB$DATABASE
  UNION ALL SELECT 'Подоконник осина 40мм', 20000 FROM RDB$DATABASE
  UNION ALL SELECT 'Наличник сосна 20мм', 10000 FROM RDB$DATABASE
  UNION ALL SELECT 'Наличник лиственница 20мм', 12500 FROM RDB$DATABASE
  UNION ALL SELECT 'Наличник дуб 20мм', 15000 FROM RDB$DATABASE
  UNION ALL SELECT 'Наличник осина 20мм', 10000 FROM RDB$DATABASE
  UNION ALL SELECT 'Наличник сосна 40мм', 20000 FROM RDB$DATABASE
  UNION ALL SELECT 'Наличник лиственница 40мм', 30000 FROM RDB$DATABASE
  UNION ALL SELECT 'Наличник дуб 40мм', 35000 FROM RDB$DATABASE
  UNION ALL SELECT 'Наличник осина 40мм', 20000 FROM RDB$DATABASE
  UNION ALL SELECT 'Откос сосна 20мм', 10000 FROM RDB$DATABASE
  UNION ALL SELECT 'Откос лиственница 20мм', 12500 FROM RDB$DATABASE
  UNION ALL SELECT 'Откос дуб 20мм', 15000 FROM RDB$DATABASE
  UNION ALL SELECT 'Откос осина 20мм', 10000 FROM RDB$DATABASE
  UNION ALL SELECT 'Откос сосна 40мм', 20000 FROM RDB$DATABASE
  UNION ALL SELECT 'Откос лиственница 40мм', 30000 FROM RDB$DATABASE
  UNION ALL SELECT 'Откос дуб 40мм', 35000 FROM RDB$DATABASE
  UNION ALL SELECT 'Откос осина 40мм', 20000 FROM RDB$DATABASE
  UNION ALL SELECT 'Фальш коробка ель 50мм', 20000 FROM RDB$DATABASE
  UNION ALL SELECT 'Направляющий брусок ель 50мм', 20000 FROM RDB$DATABASE
) d
WHERE NOT EXISTS (
  SELECT 1
  FROM STUFFS s
  WHERE s.NAME = d.NAME
    AND COALESCE(s.DELETED, 0) = 0
);

INSERT INTO STUFFSETS_ITEMS (
  ID, SETID, TYPE, STUFFID, STUFFTUPLEID, STUFFSETID, STUFFPARAMID,
  RULE, QUANTITY_FORMULA, WIDTH_FORMULA, HEIGHT_FORMULA, THICK_FORMULA,
  ANGLE1_FORMULA, ANGLE2_FORMULA, INCOLOR_FORMULA, OUTCOLOR_FORMULA,
  FOLDCOLOR_FORMULA, ADDITIONAL_FORMULA, ASPART, RCOMMENT, ISPART_RULE
)
SELECT
  GEN_ID(GEN_STUFFSETS_ITEMS, 1),
  d.SET_ID,
  0,
  s.ID,
  NULL,
  NULL,
  NULL,
  CAST(d.RULE_TXT AS BLOB SUB_TYPE TEXT),
  si.QUANTITY_FORMULA,
  si.WIDTH_FORMULA,
  si.HEIGHT_FORMULA,
  si.THICK_FORMULA,
  si.ANGLE1_FORMULA,
  si.ANGLE2_FORMULA,
  si.INCOLOR_FORMULA,
  si.OUTCOLOR_FORMULA,
  si.FOLDCOLOR_FORMULA,
  si.ADDITIONAL_FORMULA,
  si.ASPART,
  'расчетная масса',
  si.ISPART_RULE
FROM (
  SELECT 66 AS SET_ID, 1993 AS SOURCE_ITEM_ID, CAST('Коробка сосна 40мм' AS VARCHAR(128)) AS NAME,
         CAST('(arch.Code = ''Нет'') and (inrange(Wood.Code, ''Сосна Люкс'', ''Сосна сращенный''))' AS VARCHAR(1024)) AS RULE_TXT
  FROM RDB$DATABASE
  UNION ALL SELECT 66, 1993, 'Коробка лиственница 40мм',
         '(arch.Code = ''Нет'') and (inrange(Wood.Code, ''Лиственница Люкс'', ''Лиственница сращенный''))'
  FROM RDB$DATABASE
  UNION ALL SELECT 66, 1993, 'Коробка дуб 40мм',
         '(arch.Code = ''Нет'') and (inrange(Wood.Code, ''Дуб Люкс'', ''Дуб сращенный''))'
  FROM RDB$DATABASE
  UNION ALL SELECT 66, 1993, 'Коробка осина 40мм',
         '(arch.Code = ''Нет'') and (Wood.Code = ''Осина сращенный'')'
  FROM RDB$DATABASE

  UNION ALL SELECT 67, 2002, 'Подоконник сосна 40мм',
         'inrange(Wood.Code, ''Сосна Люкс'', ''Сосна сращенный'')'
  FROM RDB$DATABASE
  UNION ALL SELECT 67, 2002, 'Подоконник лиственница 40мм',
         'inrange(Wood.Code, ''Лиственница Люкс'', ''Лиственница сращенный'')'
  FROM RDB$DATABASE
  UNION ALL SELECT 67, 2002, 'Подоконник дуб 40мм',
         'inrange(Wood.Code, ''Дуб Люкс'', ''Дуб сращенный'')'
  FROM RDB$DATABASE
  UNION ALL SELECT 67, 2002, 'Подоконник осина 40мм',
         'Wood.Code = ''Осина сращенный'''
  FROM RDB$DATABASE

  UNION ALL SELECT 68, 2009, 'Наличник сосна 20мм',
         '(T <= 20) and (inrange(Wood.Code, ''Сосна Люкс'', ''Сосна сращенный''))'
  FROM RDB$DATABASE
  UNION ALL SELECT 68, 2009, 'Наличник лиственница 20мм',
         '(T <= 20) and (inrange(Wood.Code, ''Лиственница Люкс'', ''Лиственница сращенный''))'
  FROM RDB$DATABASE
  UNION ALL SELECT 68, 2009, 'Наличник дуб 20мм',
         '(T <= 20) and (inrange(Wood.Code, ''Дуб Люкс'', ''Дуб сращенный''))'
  FROM RDB$DATABASE
  UNION ALL SELECT 68, 2009, 'Наличник осина 20мм',
         '(T <= 20) and (Wood.Code = ''Осина сращенный'')'
  FROM RDB$DATABASE
  UNION ALL SELECT 68, 2010, 'Наличник сосна 40мм',
         '(T > 20) and (inrange(Wood.Code, ''Сосна Люкс'', ''Сосна сращенный''))'
  FROM RDB$DATABASE
  UNION ALL SELECT 68, 2010, 'Наличник лиственница 40мм',
         '(T > 20) and (inrange(Wood.Code, ''Лиственница Люкс'', ''Лиственница сращенный''))'
  FROM RDB$DATABASE
  UNION ALL SELECT 68, 2010, 'Наличник дуб 40мм',
         '(T > 20) and (inrange(Wood.Code, ''Дуб Люкс'', ''Дуб сращенный''))'
  FROM RDB$DATABASE
  UNION ALL SELECT 68, 2010, 'Наличник осина 40мм',
         '(T > 20) and (Wood.Code = ''Осина сращенный'')'
  FROM RDB$DATABASE

  UNION ALL SELECT 70, 2026, 'Откос сосна 20мм',
         '(T <= 20) and (inrange(Wood.Code, ''Сосна Люкс'', ''Сосна сращенный''))'
  FROM RDB$DATABASE
  UNION ALL SELECT 70, 2026, 'Откос лиственница 20мм',
         '(T <= 20) and (inrange(Wood.Code, ''Лиственница Люкс'', ''Лиственница сращенный''))'
  FROM RDB$DATABASE
  UNION ALL SELECT 70, 2026, 'Откос дуб 20мм',
         '(T <= 20) and (inrange(Wood.Code, ''Дуб Люкс'', ''Дуб сращенный''))'
  FROM RDB$DATABASE
  UNION ALL SELECT 70, 2026, 'Откос осина 20мм',
         '(T <= 20) and (Wood.Code = ''Осина сращенный'')'
  FROM RDB$DATABASE
  UNION ALL SELECT 70, 2027, 'Откос сосна 40мм',
         '(T > 20) and (inrange(Wood.Code, ''Сосна Люкс'', ''Сосна сращенный''))'
  FROM RDB$DATABASE
  UNION ALL SELECT 70, 2027, 'Откос лиственница 40мм',
         '(T > 20) and (inrange(Wood.Code, ''Лиственница Люкс'', ''Лиственница сращенный''))'
  FROM RDB$DATABASE
  UNION ALL SELECT 70, 2027, 'Откос дуб 40мм',
         '(T > 20) and (inrange(Wood.Code, ''Дуб Люкс'', ''Дуб сращенный''))'
  FROM RDB$DATABASE
  UNION ALL SELECT 70, 2027, 'Откос осина 40мм',
         '(T > 20) and (Wood.Code = ''Осина сращенный'')'
  FROM RDB$DATABASE

  UNION ALL SELECT 73, 2052, 'Фальш коробка ель 50мм', CAST(NULL AS VARCHAR(1024)) FROM RDB$DATABASE
  UNION ALL SELECT 74, 2054, 'Направляющий брусок ель 50мм', CAST(NULL AS VARCHAR(1024)) FROM RDB$DATABASE
) d
JOIN STUFFS s ON s.NAME = d.NAME AND COALESCE(s.DELETED, 0) = 0
JOIN STUFFSETS_ITEMS si ON si.ID = d.SOURCE_ITEM_ID
WHERE NOT EXISTS (
  SELECT 1
  FROM STUFFSETS_ITEMS existing_si
  WHERE existing_si.SETID = d.SET_ID
    AND existing_si.STUFFID = s.ID
);

COMMIT;
