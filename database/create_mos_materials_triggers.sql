/*
  Скрипт для создания системы переноса материалов москитных сеток
  Автор: Claude Code
  Дата: 2025-12-01

  Описание:
  - Создает сводную таблицу OUTLAYDETAIL_MOS_MATERIALS для хранения удаленных материалов москиток
  - Создает триггер SAVE_MOS_MATERIALS_BD для сохранения материалов перед удалением
  - Триггер DELETE_MOS_STUFFS удалит материалы, но они останутся в сводной таблице
  - Каскадное удаление очистит сводную таблицу при удалении OUTLAY
*/

SET TERM ^ ;

/* ========================================
   1. СОЗДАНИЕ ТАБЛИЦЫ (уже выполнено через MCP)
   ======================================== */

-- CREATE TABLE OUTLAYDETAIL_MOS_MATERIALS (
--     ID INTEGER NOT NULL PRIMARY KEY,
--     OUTLAYID INTEGER NOT NULL,
--     OUTLAYDETAILID INTEGER,
--     GOODSID INTEGER NOT NULL,
--     QTY BIGINT NOT NULL,
--     MEASUREID INTEGER NOT NULL,
--     GRORDERID INTEGER,
--     GGTYPEID INTEGER,
--     DATECREATED TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
--     CONSTRAINT FK_ODMOS_OUTLAY FOREIGN KEY (OUTLAYID) REFERENCES OUTLAY(OUTLAYID) ON DELETE CASCADE,
--     CONSTRAINT FK_ODMOS_GOODS FOREIGN KEY (GOODSID) REFERENCES GOODS(GOODSID)
-- )^

-- CREATE GENERATOR GEN_OUTLAYDETAIL_MOS_MAT^

-- CREATE INDEX IDX_ODMOS_OUTLAYID ON OUTLAYDETAIL_MOS_MATERIALS(OUTLAYID)^
-- CREATE INDEX IDX_ODMOS_GRORDERID ON OUTLAYDETAIL_MOS_MATERIALS(GRORDERID)^
-- CREATE INDEX IDX_ODMOS_GGTYPEID ON OUTLAYDETAIL_MOS_MATERIALS(GGTYPEID)^

/* ========================================
   2. ТРИГГЕР ДЛЯ СОХРАНЕНИЯ МАТЕРИАЛОВ МОСКИТОК
      Выполняется ПЕРЕД DELETE_MOS_STUFFS
   ======================================== */

CREATE TRIGGER SAVE_MOS_MATERIALS_BD
FOR OUTLAYDETAIL
ACTIVE BEFORE DELETE
POSITION 0  /* Выполнится перед DELETE_MOS_STUFFS (position 1) */
AS
DECLARE VARIABLE v_grorderid INTEGER;
DECLARE VARIABLE v_ggtypeid INTEGER;
BEGIN
  /* Получаем GRORDERID из OUTLAY */
  SELECT o.GRORDERID
  FROM OUTLAY o
  WHERE o.OUTLAYID = OLD.OUTLAYID
  INTO :v_grorderid;

  /* Если это списание к СЗ конструкций */
  IF (v_grorderid IS NOT NULL) THEN
  BEGIN
    /* Получаем тип группы материала */
    SELECT gg.GGTYPEID
    FROM GOODS g
    JOIN GROUPGOODS gg ON gg.GRGOODSID = g.GRGOODSID
    WHERE g.GOODSID = OLD.GOODSID
    INTO :v_ggtypeid;

    /* Проверяем, является ли материал москиткой */
    IF (EXISTS(
      SELECT 1 FROM GROUPGOODSTYPES ggt
      WHERE ggt.GGTYPEID = :v_ggtypeid
        AND ggt.CODE IN ('MosNetShnur', 'MosNetShip', 'MosNet')
    )) THEN
    BEGIN
      /* Сохраняем материал в сводную таблицу */
      INSERT INTO OUTLAYDETAIL_MOS_MATERIALS (
        ID, OUTLAYID, OUTLAYDETAILID, GOODSID, QTY,
        MEASUREID, GRORDERID, GGTYPEID, DATECREATED
      ) VALUES (
        GEN_ID(GEN_OUTLAYDETAIL_MOS_MAT, 1),
        OLD.OUTLAYID,
        OLD.OUTLAYDETAILID,
        OLD.GOODSID,
        OLD.QTY,
        OLD.MEASUREID,
        :v_grorderid,
        :v_ggtypeid,
        CURRENT_TIMESTAMP
      );
    END
  END
END^

/* ========================================
   3. ТРИГГЕР ДЛЯ ОЧИСТКИ ПРИ ПОМЕТКЕ OUTLAY НА УДАЛЕНИЕ
   ======================================== */

CREATE TRIGGER CLEAN_MOS_MAT_ON_OUTLAY_DELETE
FOR OUTLAY
ACTIVE AFTER UPDATE
POSITION 0
AS
BEGIN
  /* Если OUTLAY помечен на удаление (DELETED = 1), удаляем связанные материалы */
  IF (NEW.DELETED = 1 AND OLD.DELETED = 0) THEN
  BEGIN
    DELETE FROM OUTLAYDETAIL_MOS_MATERIALS
    WHERE OUTLAYID = NEW.OUTLAYID;
  END
END^

SET TERM ; ^

COMMIT;

/* ========================================
   ИНСТРУКЦИЯ ПО ПРИМЕНЕНИЮ
   ========================================

1. Таблица OUTLAYDETAIL_MOS_MATERIALS уже создана через MCP Firebird
2. Выполните этот скрипт через FlameRobin, IBExpert или другой клиент Firebird
3. После создания триггеров проверьте их наличие:

   SELECT RDB$TRIGGER_NAME, RDB$TRIGGER_TYPE, RDB$TRIGGER_SEQUENCE
   FROM RDB$TRIGGERS
   WHERE RDB$RELATION_NAME = 'OUTLAYDETAIL'
   ORDER BY RDB$TRIGGER_TYPE, RDB$TRIGGER_SEQUENCE;

4. Проверьте работу:
   - При удалении материала москитки из OUTLAYDETAIL триггером DELETE_MOS_STUFFS,
     материал сначала сохранится в OUTLAYDETAIL_MOS_MATERIALS
   - При удалении или пометке OUTLAY на удаление, связанные записи очистятся

5. После этого обновите код Python для работы со сводной таблицей

*/
