"""
Функции для работы с базой данных Altawin
"""

import fdb
from modules.config import DB_CONFIG, ENABLE_LOGGING
from modules.models import Profile, Stock, MoskitkaProfile, StockRemainder, StockMaterial, GrordersMos, OptimizedMos, OptDetailMos
from typing import List, Dict, Any

def get_db_connection():
    """
    Получить соединение с базой данных Firebird
    """
    try:
        con = fdb.connect(
            host=DB_CONFIG['host'],
            port=DB_CONFIG['port'],
            database=DB_CONFIG['database'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            charset=DB_CONFIG['charset']
        )
        return con
    except Exception as e:
        if ENABLE_LOGGING:
            print(f"Ошибка подключения к БД: {e}")
        raise

def get_profiles_for_order(order_id: int) -> List[Profile]:
    """
    Получить список профилей для распила из заказа
    """
    profiles = []
    
    try:
        con = get_db_connection()
        cur = con.cursor()
        
        # SQL запрос от Артема для получения профилей
        sql = """
        SELECT
            gr.ordernames as gr_ordernames,
            gr.groupdate as groupdate,
            gr.name as gr_name,
            oi.orderitemsid,
            oi.name as oi_name,
            o.orderno,
            g.marking as g_marking,
            g.goodsid,
            grd.qty * itd.qty as total_qty,
            itd.thick
        FROM grorders gr
        JOIN grordersdetail grd on grd.grorderid = gr.grorderid
        JOIN orderitems oi on oi.orderitemsid = grd.orderitemsid
        JOIN orders o on o.orderid = oi.orderid
        JOIN itemsdetail itd on itd.orderitemsid = oi.orderitemsid
        JOIN goods g on g.goodsid = itd.goodsid
        JOIN groupgoods gg on gg.grgoodsid = itd.grgoodsid
        JOIN groupgoodstypes ggt on ggt.ggtypeid = gg.ggtypeid
        WHERE gr.grorderid = ?
        AND ggt.code = 'MosNetProfile'
        AND gg.thick <> 1
        ORDER BY oi.orderitemsid
        """
        
        cur.execute(sql, (order_id,))
        rows = cur.fetchall()
        
        for row in rows:
            profile = Profile(
                id=row[7],  # goodsid
                order_id=order_id,
                element_name=row[4] or "",  # oi_name - Элемент (наименование orderitem)
                profile_code=row[6],  # g_marking - Артикул профиля
                length=float(row[9]),  # thick (длина)
                quantity=int(row[8])  # total_qty - Количество
            )
            profiles.append(profile)
        
        con.close()
        
        if ENABLE_LOGGING:
            print(f"✅ Получено {len(profiles)} профилей для заказа {order_id}")
            
    except Exception as e:
        if ENABLE_LOGGING:
            print(f"❌ Ошибка получения профилей: {e}")
        raise
    
    return profiles

def get_grorder_ids_by_grorders_mos_id(grorders_mos_id: int) -> List[int]:
    """
    Получить список GRORDERID по идентификатору сменного задания москитных сеток (GRORDERS_MOS_ID).

    Логика: связь хранится в таблице GRORDER_UF_VALUES по userfieldid = 8 и var_str = grorders_mos_id.
    """
    grorder_ids: List[int] = []
    try:
        con = get_db_connection()
        cur = con.cursor()

        sql = (
            "SELECT gruv.GRORDERID "
            "FROM GRORDER_UF_VALUES gruv "
            "WHERE gruv.USERFIELDID = 8 AND gruv.VAR_STR = ?"
        )

        # Приводим к строке, т.к. столбец VAR_STR текстовый
        cur.execute(sql, (str(grorders_mos_id),))
        rows = cur.fetchall()

        for row in rows:
            if row and row[0] is not None:
                grorder_ids.append(int(row[0]))

        con.close()

        if ENABLE_LOGGING:
            print(
                f"✅ Получено {len(grorder_ids)} GRORDERID по GRORDERS_MOS_ID={grorders_mos_id}: {grorder_ids}"
            )
    except Exception as e:
        if ENABLE_LOGGING:
            print(f"❌ Ошибка получения GRORDERID по GRORDERS_MOS_ID={grorders_mos_id}: {e}")
        raise

    return grorder_ids

def get_stock_for_profile(profile_id: int) -> List[Stock]:
    """
    Получить остатки профиля на складе
    Возвращает остатки профилей (обрезки) и основной склад (хлысты)
    """
    stock = []
    
    try:
        con = get_db_connection()
        cur = con.cursor()
        
        # Первый запрос - хлысты из основного склада
        sql_warehouse = """
        SELECT 
            wh.WAREHOUSEID as stock_id,
            wh.GOODSID,
            6000 as length,
            wh.QTY - wh.RESERVEQTY as qty,
            whl.RNAME as location,
            0 as is_remainder,
            g.MARKING as profile_code
        FROM WAREHOUSE wh
        JOIN WH_LIST whl ON whl.WHLISTID = wh.WHLISTID
        JOIN GOODS g ON g.GOODSID = wh.GOODSID
        WHERE wh.GOODSID = ? 
        AND (wh.QTY - wh.RESERVEQTY) > 0
        AND whl.DELETED = 0
        AND g.DELETED = 0
        """
        
        cur.execute(sql_warehouse, (profile_id,))
        warehouse_rows = cur.fetchall()
        
        # Второй запрос - остатки
        sql_remainders = """
        SELECT 
            whr.WHREMAINDERID as stock_id,
            whr.GOODSID,
            whr.THICK as length,
            whr.QTY - whr.RESERVEQTY as qty,
            whl.RNAME as location,
            1 as is_remainder,
            g.MARKING as profile_code
        FROM WAREHOUSEREMAINDER whr
        JOIN WH_LIST whl ON whl.WHLISTID = whr.WHLISTID
        JOIN GOODS g ON g.GOODSID = whr.GOODSID
        WHERE whr.GOODSID = ?
        AND (whr.QTY - whr.RESERVEQTY) > 0
        AND whl.DELETED = 0
        AND g.DELETED = 0
        """
        
        cur.execute(sql_remainders, (profile_id,))
        remainder_rows = cur.fetchall()
        
        # Объединяем результаты
        all_rows = list(warehouse_rows) + list(remainder_rows)
        
        for row in all_rows:
            stock_item = Stock(
                id=row[0],  # stock_id
                profile_id=row[1],  # goodsid
                length=float(row[2]) if row[2] else 6000.0,  # length
                quantity=int(row[3]),  # qty
                location=row[4] or "",  # location
                is_remainder=bool(row[5])  # is_remainder
            )
            stock.append(stock_item)
        
        con.close()
        
        # Сортируем результат: сначала хлысты (is_remainder=False), потом остатки по длине убывающей
        stock.sort(key=lambda x: (x.is_remainder, -x.length))
        
        if ENABLE_LOGGING:
            print(f"✅ Получено {len(stock)} позиций на складе для профиля {profile_id}")
            
    except Exception as e:
        if ENABLE_LOGGING:
            print(f"❌ Ошибка получения остатков: {e}")
        raise
    
    return stock

def get_stock_remainders(profile_codes: List[str]) -> List[StockRemainder]:
    """
    Получить остатки со склада по артикулам профилей
    """
    stock_remainders = []
    
    if not profile_codes:
        return stock_remainders
    
    try:
        con = get_db_connection()
        cur = con.cursor()
        
        # Создаем строку для IN условия
        placeholders = ','.join(['?'] * len(profile_codes))
        
        sql = f"""
        SELECT 
            g.MARKING as profile_code,
            whr.THICK as length,
            COUNT(whr.WHREMAINDERID) as quantity_pieces
        FROM WAREHOUSEREMAINDER whr
        JOIN WH_LIST whl ON whl.WHLISTID = whr.WHLISTID
        JOIN GOODS g ON g.GOODSID = whr.GOODSID
        WHERE g.MARKING IN ({placeholders})
        AND (whr.QTY - whr.RESERVEQTY) > 0
        AND whl.DELETED = 0
        AND g.DELETED = 0
        GROUP BY g.MARKING, whr.THICK
        ORDER BY g.MARKING, whr.THICK DESC
        """
        
        cur.execute(sql, profile_codes)
        rows = cur.fetchall()
        
        for row in rows:
            remainder = StockRemainder(
                profile_code=row[0],  # profile_code
                length=float(row[1]) if row[1] else 0.0,  # length
                quantity_pieces=int(row[2])  # quantity_pieces - количество палок
            )
            stock_remainders.append(remainder)
        
        con.close()
        
        if ENABLE_LOGGING:
            print(f"✅ Получено {len(stock_remainders)} остатков со склада")
            
    except Exception as e:
        if ENABLE_LOGGING:
            print(f"❌ Ошибка получения остатков: {e}")
        raise
    
    return stock_remainders

def get_stock_materials(profile_codes: List[str]) -> List[StockMaterial]:
    """
    Получить цельные материалы со склада по артикулам профилей
    Количество рассчитывается как складское количество / типовой размер (аналогично Glass Optimizer)
    """
    stock_materials = []
    
    if not profile_codes:
        return stock_materials
    
    try:
        con = get_db_connection()
        cur = con.cursor()
        
        # Создаем строку для IN условия
        placeholders = ','.join(['?'] * len(profile_codes))
        
        sql = f"""
        SELECT 
            g.MARKING as profile_code,
            gg.THICK as length,
            SUM(wh.QTY - wh.RESERVEQTY) as warehouse_qty,
            gg.THICK as typical_size,
            CASE 
                WHEN gg.THICK > 0 THEN SUM(wh.QTY - wh.RESERVEQTY) / gg.THICK
                ELSE 0
            END as quantity_pieces
        FROM WAREHOUSE wh
        JOIN WH_LIST whl ON whl.WHLISTID = wh.WHLISTID
        JOIN GOODS g ON g.GOODSID = wh.GOODSID
        JOIN GROUPGOODS gg ON gg.GRGOODSID = g.GRGOODSID
        WHERE g.MARKING IN ({placeholders})
        AND (wh.QTY - wh.RESERVEQTY) > 0
        AND whl.DELETED = 0
        AND g.DELETED = 0
        AND gg.THICK > 1
        GROUP BY g.MARKING, gg.THICK
        ORDER BY g.MARKING
        """
        
        cur.execute(sql, profile_codes)
        rows = cur.fetchall()
        
        for row in rows:
            material = StockMaterial(
                profile_code=row[0],  # profile_code
                length=float(row[1]) if row[1] else 6000.0,  # length (типовой размер из gg.LENGTH)
                quantity_pieces=int(row[4]) if row[4] else 0  # quantity_pieces - складское количество / типовой размер
            )
            stock_materials.append(material)
        
        con.close()
        
        if ENABLE_LOGGING:
            print(f"✅ Получено {len(stock_materials)} материалов со склада")
            
    except Exception as e:
        if ENABLE_LOGGING:
            print(f"❌ Ошибка получения материалов: {e}")
        raise
    
    return stock_materials

def save_optimization_result(optimization_result, save_to_order: bool, create_cutting_list: bool):
    """
    Сохранить результаты оптимизации в Altawin
    """
    try:
        con = get_db_connection()
        cur = con.cursor()
        
        # Начинаем транзакцию
        con.begin()
        
        # Для каждого плана распила создаем записи в LINEAROPTDATA и LINEAROPTDETAIL
        for plan in optimization_result.cut_plans:
            
            # 1. Создаем запись в LINEAROPTDATA (информация о хлысте)
            insert_optdata_sql = """
            INSERT INTO LINEAROPTDATA (
                SHIFTTASKSID, GOODSID, QTY, LONGPROF, CUTWIDTH, 
                MINREST, OSTAT, SUMPROF, RESTPERCENT, TRASHPERCENT, MAP
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            # Формируем карту распила для OPTIMIZED.MAP: список длин с одним десятичным знаком, через ';'
            pieces = []
            for cut in plan.cuts:
                length_val = float(cut['length']) if cut.get('length') else 0.0
                qty_val = int(cut['quantity']) if cut.get('quantity') else 0
                for _ in range(max(0, qty_val)):
                    pieces.append(f"{length_val:.1f}")
            cut_map = ";".join(pieces)
            
            cur.execute(insert_optdata_sql, (
                optimization_result.order_id,  # SHIFTTASKSID (ID сменного задания)
                plan.stock_id,  # GOODSID (это может быть не правильно, нужно уточнить)
                1,  # QTY (количество хлыстов этого типа)
                plan.stock_length,  # LONGPROF (длина хлыста)
                3.0,  # CUTWIDTH (ширина пропила)
                100.0,  # MINREST (минимальный остаток)
                plan.remainder or plan.waste,  # OSTAT (остаток)
                sum(cut['length'] * cut['quantity'] for cut in plan.cuts),  # SUMPROF (сумма отпиленных кусков)
                (plan.remainder or 0) / plan.stock_length * 100,  # RESTPERCENT
                plan.waste_percent,  # TRASHPERCENT
                cut_map  # MAP (карта распила)
            ))
            
            # Получаем ID созданной записи
            cur.execute("SELECT GEN_ID(GEN_LINEAROPTDATA_ID, 0) FROM RDB$DATABASE")
            linearoptdata_id = cur.fetchone()[0]
            
            # 2. Создаем записи в LINEAROPTDETAIL для каждого распила
            for cut in plan.cuts:
                insert_detail_sql = """
                INSERT INTO LINEAROPTDETAIL (
                    LINEAROPTDATAID, ITEMLONG, QTY, NUM, SUBNUM, LONG_AL
                ) VALUES (?, ?, ?, ?, ?, ?)
                """
                
                cur.execute(insert_detail_sql, (
                    linearoptdata_id,  # LINEAROPTDATAID
                    cut['length'],  # ITEMLONG (длина куска)
                    cut['quantity'],  # QTY (количество кусков)
                    1,  # NUM (номер хлыста)
                    1,  # SUBNUM (порядковый номер в хлысте)
                    cut['length'] + 3.0  # LONG_AL (длина с пилой)
                ))
        
        # Подтверждаем транзакцию
        con.commit()
        con.close()
        
        if ENABLE_LOGGING:
            print(f"✅ Результаты оптимизации сохранены: {len(optimization_result.cut_plans)} планов распила")
        
        return True
        
    except Exception as e:
        # Откатываем транзакцию при ошибке
        try:
            con.rollback()
        except:
            pass
        
        if ENABLE_LOGGING:
            print(f"❌ Ошибка сохранения результатов: {e}")
        raise

def get_moskitka_profiles(grorder_ids: List[int]) -> List[MoskitkaProfile]:
    """
    Получить информацию о профилях москитных сеток для раскроя
    
    Args:
        grorder_ids: Список ID групп заказов
        
    Returns:
        Список профилей москитных сеток с полной информацией для оптимизации
    """
    profiles = []
    
    if not grorder_ids:
        return profiles
    
    try:
        con = get_db_connection()
        cur = con.cursor()
        
        # Создаем строку для IN условия
        placeholders = ','.join(['?'] * len(grorder_ids))
        
        sql = f"""
        SELECT 
            grd.GRORDERID,
            grd.ORDERITEMSID,
            oi.NAME as ORDER_ITEM_NAME,
            grd.QTY as GRORDER_QTY,
            oi.QTY as ORDER_QTY,
            oi.WIDTH as ORDER_WIDTH,
            oi.HEIGHT as ORDER_HEIGHT,
            itd.ITEMSDETAILID,
            itd.MODELNO,
            itd.PARTNUM,
            itd.WIDTH as DETAIL_WIDTH,
            itd.HEIGHT as DETAIL_HEIGHT,
            itd.THICK as DETAIL_LENGTH,
            itd.QTY as DETAIL_QTY,
            itd.IZDPART,
            itd.PARTSIDE,
            gg.NAME as GOODS_GROUP_NAME,
            gg.MARKING as GROUP_MARKING,
            g.MARKING as GOODS_MARKING,
            p.NAME as PROFIL_NAME,
            pp.PARTNAME as PART_TYPE,
            p.LENGTH_PROF,
            p.WIDTH_PROF,
            p.THICK_PROF,
            (itd.THICK * itd.QTY * grd.QTY) as TOTAL_LENGTH_NEEDED
        FROM GRORDERSDETAIL grd
        JOIN ORDERITEMS oi ON grd.ORDERITEMSID = oi.ORDERITEMSID
        JOIN ITEMSDETAIL itd ON oi.ORDERITEMSID = itd.ORDERITEMSID
        JOIN GROUPGOODS gg ON itd.GRGOODSID = gg.GRGOODSID
        LEFT JOIN GOODS g ON itd.GOODSID = g.GOODSID
        LEFT JOIN R_PROFILS p ON g.MARKING = p.MARKING AND p.RSYSTEMID = 27
        LEFT JOIN R_PROFPARTS pp ON p.PROFPARTID = pp.PARTID
        WHERE grd.GRORDERID IN ({placeholders})
          AND gg.DELETED = 0
          AND (g.DELETED = 0 OR g.DELETED IS NULL)
          AND (p.DELETED = 0 OR p.DELETED IS NULL)
          AND p.PROFILID IS NOT NULL
        ORDER BY grd.GRORDERID, grd.ORDERITEMSID, itd.ITEMSDETAILID
        """
        
        cur.execute(sql, grorder_ids)
        rows = cur.fetchall()
        
        for row in rows:
            profile = MoskitkaProfile(
                grorder_id=row[0],
                order_item_id=row[1],
                order_item_name=row[2] or "",
                grorder_qty=row[3] or 0,
                order_qty=row[4] or 0,
                order_width=row[5],
                order_height=row[6],
                item_detail_id=row[7],
                model_no=row[8] or 0,
                part_num=row[9],
                detail_width=row[10],
                detail_height=row[11],
                detail_length=row[12],
                detail_qty=row[13],
                izd_part=row[14],
                part_side=row[15],
                goods_group_name=row[16],
                group_marking=row[17],
                goods_marking=row[18],
                profil_name=row[19],
                part_type=row[20],
                length_prof=row[21],
                width_prof=row[22],
                thick_prof=row[23],
                total_length_needed=row[24]
            )
            profiles.append(profile)
        
        con.close()
        
        if ENABLE_LOGGING:
            print(f"Найдено {len(profiles)} профилей москитных сеток для групп заказов: {grorder_ids}")
        
    except Exception as e:
        if ENABLE_LOGGING:
            print(f"Ошибка получения профилей москитных сеток: {e}")
        raise
    
    return profiles

def enrich_optdetail_mos_fields(
    *,
    optimized_mos_id: int,
    orderid: int,
    itemlong: float | None = None,
    itemsdetailid: int | None = None,
    ug1: float | None = None,
    ug2: float | None = None,
    izdpart: str | None = None,
    partside: str | None = None,
    modelno: int | None = None,
    modelheight: int | None = None,
    modelwidth: int | None = None,
    flugelopentype: int | None = None,
    flugelcount: int | None = None,
    ishandle: int | None = None,
    handlepos: float | None = None,
    handleposfalts: float | None = None,
    flugelopentag: str | None = None,
) -> Dict[str, Any]:
    """
    Обогатить поля OPTDETAIL_MOS на основании данных из БД, без модификации вставки.
    Возвращает словарь с теми же ключами, но с заполненными значениями там, где это возможно.
    """
    try:
        con = get_db_connection()
        cur = con.cursor()

        # Узнаем GOODSID по текущему OPTIMIZED_MOS
        goods_id_for_bar = None
        try:
            cur.execute(
                "SELECT GOODSID, GRORDER_MOS_ID FROM OPTIMIZED_MOS WHERE OPTIMIZED_MOS_ID = ?",
                (optimized_mos_id,),
            )
            row_goods = cur.fetchone()
            goods_id_for_bar = int(row_goods[0]) if row_goods and row_goods[0] is not None else None
            grorders_mos_id = int(row_goods[1]) if row_goods and row_goods[1] is not None else None
        except Exception:
            goods_id_for_bar = None
            grorders_mos_id = None

        # 1) Пробуем найти ITEMSDETAIL для данного заказа и материала (или по длине)
        try:
            if itemsdetailid is None:
                # 1.1) Сначала трактуем orderid как GRORDERID (для MOS это верно)
                if orderid and goods_id_for_bar:
                    target_length = float(itemlong or 0)
                    cur.execute(
                        (
                            "SELECT FIRST 1 itd.ITEMSDETAILID, itd.ANG1, itd.ANG2, itd.IZDPART, itd.PARTSIDE, itd.MODELNO, "
                            "oi.WIDTH AS O_WIDTH, oi.HEIGHT AS O_HEIGHT, itd.WIDTH AS D_WIDTH, itd.HEIGHT AS D_HEIGHT, itd.THICK "
                            "FROM GRORDERSDETAIL grd "
                            "JOIN ORDERITEMS oi ON oi.ORDERITEMSID = grd.ORDERITEMSID "
                            "JOIN ITEMSDETAIL itd ON itd.ORDERITEMSID = oi.ORDERITEMSID "
                            "WHERE grd.GRORDERID = ? AND itd.GOODSID = ? "
                            "ORDER BY ABS(COALESCE(itd.THICK, 0) - ?) ASC, itd.ITEMSDETAILID DESC"
                        ),
                        (int(orderid), goods_id_for_bar, target_length),
                    )
                    cand_gr = cur.fetchone()
                    if cand_gr:
                        itemsdetailid = int(cand_gr[0])
                        if ug1 is None:
                            ug1 = float(cand_gr[1]) if cand_gr[1] is not None else None
                        if ug2 is None:
                            ug2 = float(cand_gr[2]) if cand_gr[2] is not None else None
                        # Поменяли местами: izdpart <- PARTSIDE, partside <- IZDPART
                        # Поменяли местами: izdpart <- PARTSIDE, partside <- IZDPART (только если источник не пустой)
                        if (izdpart is None or (isinstance(izdpart, str) and izdpart.strip() == "")) and (cand_gr[4] is not None and str(cand_gr[4]).strip() != ""):
                            izdpart = cand_gr[4]
                        if (partside is None or (isinstance(partside, str) and partside.strip() == "")) and (cand_gr[3] is not None and str(cand_gr[3]).strip() != ""):
                            partside = cand_gr[3]
                        if modelno is None:
                            modelno = int(cand_gr[5]) if cand_gr[5] is not None else None
                        if modelwidth is None:
                            modelwidth = int(cand_gr[6]) if cand_gr[6] is not None else (int(cand_gr[8]) if cand_gr[8] is not None else None)
                        if modelheight is None:
                            modelheight = int(cand_gr[7]) if cand_gr[7] is not None else (int(cand_gr[9]) if cand_gr[9] is not None else None)

                if orderid and goods_id_for_bar:
                    target_length = float(itemlong or 0)
                    cur.execute(
                        (
                            "SELECT FIRST 1 itd.ITEMSDETAILID, itd.ANG1, itd.ANG2, itd.IZDPART, itd.PARTSIDE, "
                            "itd.MODELNO, oi.WIDTH AS O_WIDTH, oi.HEIGHT AS O_HEIGHT, itd.WIDTH AS D_WIDTH, itd.HEIGHT AS D_HEIGHT, itd.THICK "
                            "FROM ITEMSDETAIL itd "
                            "JOIN ORDERITEMS oi ON oi.ORDERITEMSID = itd.ORDERITEMSID "
                            "WHERE oi.ORDERID = ? AND (itd.GOODSID = ?) "
                            "ORDER BY ABS(COALESCE(itd.THICK, 0) - ?) ASC, itd.ITEMSDETAILID DESC"
                        ),
                        (orderid, goods_id_for_bar, target_length),
                    )
                    cand = cur.fetchone()
                    if cand:
                        itemsdetailid = int(cand[0])
                        if ug1 is None:
                            ug1 = float(cand[1]) if cand[1] is not None else None
                        if ug2 is None:
                            ug2 = float(cand[2]) if cand[2] is not None else None
                        # Поменяли местами: izdpart <- PARTSIDE, partside <- IZDPART
                        if (izdpart is None or (isinstance(izdpart, str) and izdpart.strip() == "")) and (cand[4] is not None and str(cand[4]).strip() != ""):
                            izdpart = cand[4]
                        if (partside is None or (isinstance(partside, str) and partside.strip() == "")) and (cand[3] is not None and str(cand[3]).strip() != ""):
                            partside = cand[3]
                        if modelno is None:
                            modelno = int(cand[5]) if cand[5] is not None else None
                        # HEIGHT/WIDTH: сперва из ORDERITEMS, затем из ITEMSDETAIL
                        if modelwidth is None:
                            modelwidth = int(cand[6]) if cand[6] is not None else (int(cand[8]) if cand[8] is not None else None)
                        if modelheight is None:
                            modelheight = int(cand[7]) if cand[7] is not None else (int(cand[9]) if cand[9] is not None else None)

                if itemsdetailid is None and orderid and itemlong is not None:
                    cur.execute(
                        (
                            "SELECT FIRST 1 itd.ITEMSDETAILID FROM ITEMSDETAIL itd "
                            "JOIN ORDERITEMS oi ON oi.ORDERITEMSID = itd.ORDERITEMSID "
                            "WHERE oi.ORDERID = ? "
                            "ORDER BY ABS(COALESCE(itd.THICK, 0) - ?) ASC, itd.ITEMSDETAILID DESC"
                        ),
                        (orderid, float(itemlong)),
                    )
                    row_fallback = cur.fetchone()
                    if row_fallback and row_fallback[0] is not None:
                        itemsdetailid = int(row_fallback[0])

                # MOS-путь: ищем по GRORDER_MOS_ID -> GRORDERID
                if itemsdetailid is None and goods_id_for_bar is not None and grorders_mos_id is not None:
                    cur.execute(
                        "SELECT GRORDERID FROM GRORDER_UF_VALUES WHERE USERFIELDID = 8 AND VAR_STR = ?",
                        (str(grorders_mos_id),),
                    )
                    gr_rows = cur.fetchall() or []
                    gr_ids = [int(r[0]) for r in gr_rows if r and r[0] is not None]
                    if gr_ids:
                        placeholders = ",".join(["?"] * len(gr_ids))
                        target_length = float(itemlong or 0)
                        sql = (
                            "SELECT FIRST 1 itd.ITEMSDETAILID, itd.ANG1, itd.ANG2, itd.IZDPART, itd.PARTSIDE, itd.MODELNO, "
                            "oi.WIDTH AS O_WIDTH, oi.HEIGHT AS O_HEIGHT, itd.WIDTH AS D_WIDTH, itd.HEIGHT AS D_HEIGHT "
                            "FROM GRORDERSDETAIL grd "
                            "JOIN ORDERITEMS oi ON oi.ORDERITEMSID = grd.ORDERITEMSID "
                            "JOIN ITEMSDETAIL itd ON itd.ORDERITEMSID = oi.ORDERITEMSID "
                            f"WHERE grd.GRORDERID IN ({placeholders}) AND itd.GOODSID = ? "
                            "ORDER BY ABS(COALESCE(itd.THICK, 0) - ?) ASC, itd.ITEMSDETAILID DESC"
                        )
                        params = gr_ids + [goods_id_for_bar, target_length]
                        cur.execute(sql, params)
                        cand2 = cur.fetchone()
                        if cand2:
                            itemsdetailid = int(cand2[0])
                            if ug1 is None:
                                ug1 = float(cand2[1]) if cand2[1] is not None else None
                            if ug2 is None:
                                ug2 = float(cand2[2]) if cand2[2] is not None else None
                            # Поменяли местами: izdpart <- PARTSIDE, partside <- IZDPART
                            if (izdpart is None or (isinstance(izdpart, str) and izdpart.strip() == "")) and (cand2[4] is not None and str(cand2[4]).strip() != ""):
                                izdpart = cand2[4]
                            if (partside is None or (isinstance(partside, str) and partside.strip() == "")) and (cand2[3] is not None and str(cand2[3]).strip() != ""):
                                partside = cand2[3]
                            if modelno is None:
                                modelno = int(cand2[5]) if cand2[5] is not None else None
                            if modelwidth is None:
                                modelwidth = int(cand2[6]) if cand2[6] is not None else (int(cand2[8]) if cand2[8] is not None else None)
                            if modelheight is None:
                                modelheight = int(cand2[7]) if cand2[7] is not None else (int(cand2[9]) if cand2[9] is not None else None)
        except Exception as _:
            pass

        # 2) Дополняем углы/части/стороны и flugel*/handle* из OPTDETAIL / MODELPARTS
        try:
            if itemsdetailid is not None:
                # 2.0) Если UG1/UG2/IZDPART/PARTSIDE ещё пустые — возьмём из OPTDETAIL
                need_fill_angles_parts = (
                    ug1 is None
                    or ug2 is None
                    or izdpart is None
                    or (isinstance(izdpart, str) and izdpart.strip() == "")
                    or partside is None
                    or (isinstance(partside, str) and partside.strip() == "")
                )
                if need_fill_angles_parts:
                    cur.execute(
                        (
                            "SELECT FIRST 1 UG1, UG2, IZDPART, PARTSIDE "
                            "FROM OPTDETAIL WHERE ITEMSDETAILID = ? ORDER BY OPTDETAILID DESC"
                        ),
                        (itemsdetailid,),
                    )
                    od_angles = cur.fetchone()
                    if od_angles:
                        if ug1 is None:
                            ug1 = od_angles[0]
                        if ug2 is None:
                            ug2 = od_angles[1]
                        # Поменяли местами: izdpart <- PARTSIDE, partside <- IZDPART (только если источник не пустой)
                        if (izdpart is None or (isinstance(izdpart, str) and izdpart.strip() == "")) and (od_angles[3] is not None and str(od_angles[3]).strip() != ""):
                            izdpart = od_angles[3]
                        if (partside is None or (isinstance(partside, str) and partside.strip() == "")) and (od_angles[2] is not None and str(od_angles[2]).strip() != ""):
                            partside = od_angles[2]

                if (
                    flugelopentype is None
                    or flugelcount is None
                    or ishandle is None
                    or handlepos is None
                    or handleposfalts is None
                    or flugelopentag is None
                ):
                    cur.execute(
                        (
                            "SELECT FIRST 1 FLUGELOPENTYPE, FLUGELCOUNT, ISHANDLE, HANDLEPOS, HANDLEPOSFALTS, FLUGELOPENTAG "
                            "FROM OPTDETAIL WHERE ITEMSDETAILID = ? ORDER BY OPTDETAILID DESC"
                        ),
                        (itemsdetailid,),
                    )
                    od = cur.fetchone()
                    if od:
                        if flugelopentype is None:
                            flugelopentype = od[0]
                        if flugelcount is None:
                            flugelcount = od[1]
                        if ishandle is None:
                            ishandle = od[2]
                        if handlepos is None:
                            handlepos = od[3]
                        if handleposfalts is None:
                            handleposfalts = od[4]
                        if flugelopentag is None:
                            flugelopentag = od[5]

                if flugelopentype is None or flugelopentag is None:
                    cur.execute(
                        "SELECT MODELPARTID FROM ITEMSDETAIL WHERE ITEMSDETAILID = ?",
                        (itemsdetailid,),
                    )
                    mp = cur.fetchone()
                    modelpartid = mp[0] if mp else None
                    if modelpartid is not None:
                        cur.execute(
                            (
                                "SELECT FLUGELOPENTYPE, FLUGELOPENTAG FROM MODELPARTS WHERE PARTID = ?"
                            ),
                            (modelpartid,),
                        )
                        mpd = cur.fetchone()
                        if mpd:
                            if flugelopentype is None:
                                flugelopentype = mpd[0]
                            if flugelopentag is None:
                                flugelopentag = mpd[1]
        except Exception as _:
            pass

        con.close()
    except Exception as e:
        if ENABLE_LOGGING:
            print(f"Предупреждение: enrich_optdetail_mos_fields не удалось полностью: {e}")

    return {
        "itemsdetailid": itemsdetailid,
        "ug1": ug1,
        "ug2": ug2,
        "izdpart": izdpart,
        "partside": partside,
        "modelno": modelno,
        "modelheight": modelheight,
        "modelwidth": modelwidth,
        "flugelopentype": flugelopentype,
        "flugelcount": flugelcount,
        "ishandle": ishandle,
        "handlepos": handlepos,
        "handleposfalts": handleposfalts,
        "flugelopentag": flugelopentag,
    }

def test_db_connection():
    """
    Проверить соединение с базой данных
    """
    try:
        con = get_db_connection()
        cur = con.cursor()
        cur.execute("SELECT 1 FROM RDB$DATABASE")
        result = cur.fetchone()
        con.close()
        return result is not None
    except Exception as e:
        return False 


def insert_grorders_mos(name: str) -> GrordersMos:
    """
    Вставить запись в таблицу GRORDERS_MOS и вернуть созданную запись
    Использует генератор GEN_GRORDERS_MOS_ID для получения нового ID
    """
    try:
        con = get_db_connection()
        cur = con.cursor()

        # Начинаем транзакцию
        con.begin()

        # Получаем новый ID из генератора
        cur.execute("SELECT GEN_ID(GEN_GRORDERS_MOS_ID, 1) FROM RDB$DATABASE")
        new_id_row = cur.fetchone()
        new_id = int(new_id_row[0]) if new_id_row and new_id_row[0] is not None else None

        # Простой INSERT по аналогии с другими функциями
        insert_sql = """
        INSERT INTO GRORDERS_MOS (ID, NAME)
        VALUES (?, ?)
        """
        cur.execute(insert_sql, (new_id, name))

        # Фиксируем транзакцию
        con.commit()
        con.close()

        return GrordersMos(id=new_id, name=name)
    except Exception as e:
        try:
            con.rollback()
        except:
            pass
        if ENABLE_LOGGING:
            print(f"Ошибка вставки в GRORDERS_MOS: {e}")
        raise


def insert_optimized_mos(
    *,
    grorder_mos_id: int,
    goodsid: int,
    qty: int,
    isbar: int,
    longprof: float | None = None,
    cutwidth: int | None = None,
    border: int | None = None,
    minrest: int | None = None,
    mintrash: int | None = None,
    map: str | None = None,
    ostat: float | None = None,
    sumprof: float | None = None,
    restpercent: float | None = None,
    trashpercent: float | None = None,
    beginindent: int | None = None,
    endindent: int | None = None,
    sumtrash: float | None = None,
) -> OptimizedMos:
    """
    Вставка записи в OPTIMIZED_MOS. Возвращает созданную запись.
    Используем генератор GEN_OPTIMIZED_MOS_ID и явный INSERT по аналогии с другими функциями.
    Обязательные поля: GRORDER_MOS_ID, GOODSID, QTY, ISBAR
    """
    try:
        con = get_db_connection()
        cur = con.cursor()

        con.begin()

        # Получаем новый ID
        cur.execute("SELECT GEN_ID(GEN_OPTIMIZED_MOS_ID, 1) FROM RDB$DATABASE")
        new_id_row = cur.fetchone()
        new_id = int(new_id_row[0]) if new_id_row and new_id_row[0] is not None else None

        insert_sql = (
            "INSERT INTO OPTIMIZED_MOS ("
            "OPTIMIZED_MOS_ID, GRORDER_MOS_ID, GOODSID, QTY, LONGPROF, CUTWIDTH, BORDER, MINREST, MINTRASH, MAP, ISFORPAIR, OSTAT, SUMPROF, RESTPERCENT, TRASHPERCENT, BEGININDENT, ENDINDENT, SUMTRASH, ISBAR"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        )

        cur.execute(
            insert_sql,
            (
                new_id,
                grorder_mos_id,
                goodsid,
                qty,
                longprof,
                cutwidth,
                border,
                minrest,
                mintrash,
                map,
                0,  # ISFORPAIR по умолчанию 0, если не требуется иное
                ostat,
                sumprof,
                restpercent,
                trashpercent,
                beginindent,
                endindent,
                sumtrash,
                isbar,
            ),
        )

        con.commit()
        con.close()

        return OptimizedMos(
            id=new_id,
            grorder_mos_id=grorder_mos_id,
            goodsid=goodsid,
            qty=qty,
            longprof=longprof,
            cutwidth=cutwidth,
            border=border,
            minrest=minrest,
            mintrash=mintrash,
            map=map,
            isbar=isbar,
            ostat=ostat,
            sumprof=sumprof,
            restpercent=restpercent,
            trashpercent=trashpercent,
            beginindent=beginindent,
            endindent=endindent,
            sumtrash=sumtrash,
        )
    except Exception as e:
        try:
            con.rollback()
        except:
            pass
        if ENABLE_LOGGING:
            print(f"Ошибка вставки в OPTIMIZED_MOS: {e}")
        raise


def insert_optdetail_mos(
    *,
    optimized_mos_id: int,
    orderid: int,
    qty: int,
    itemsdetailid: int | None = None,
    itemlong: float | None = None,
    ug1: float | None = None,
    ug2: float | None = None,
    num: int | None = None,
    subnum: int | None = None,
    long_al: float | None = None,
    izdpart: str | None = None,
    partside: str | None = None,
    modelno: int | None = None,
    modelheight: int | None = None,
    modelwidth: int | None = None,
    flugelopentype: int | None = None,
    flugelcount: int | None = None,
    ishandle: int | None = None,
    handlepos: float | None = None,
    handleposfalts: float | None = None,
    flugelopentag: str | None = None,
) -> OptDetailMos:
    """
    Вставка записи в OPTDETAIL_MOS. Возвращает созданную запись.
    Используем генератор GEN_OPTDETAIL_MOS_ID и простой INSERT.
    Обязательные поля: OPTIMIZED_MOS_ID, ORDERID, QTY
    """
    try:
        con = get_db_connection()
        cur = con.cursor()

        con.begin()

        # Получаем новый ID
        cur.execute("SELECT GEN_ID(GEN_OPTDETAIL_MOS_ID, 1) FROM RDB$DATABASE")
        new_id_row = cur.fetchone()
        new_id = int(new_id_row[0]) if new_id_row and new_id_row[0] is not None else None

        insert_sql = (
            "INSERT INTO OPTDETAIL_MOS ("
            "OPTDETAIL_MOS_ID, OPTIMIZED_MOS_ID, ORDERID, ITEMSDETAILID, ITEMLONG, QTY, UG1, UG2, NUM, SUBNUM, LONG_AL, IZDPART, PARTSIDE, MODELNO, MODELHEIGHT, MODELWIDTH, FLUGELOPENTYPE, FLUGELCOUNT, ISHANDLE, HANDLEPOS, HANDLEPOSFALTS, FLUGELOPENTAG"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        )

        cur.execute(
            insert_sql,
            (
                new_id,
                optimized_mos_id,
                orderid,
                itemsdetailid,
                itemlong,
                qty,
                ug1,
                ug2,
                num,
                subnum,
                long_al,
                izdpart,
                partside,
                modelno,
                modelheight,
                modelwidth,
                flugelopentype,
                flugelcount,
                ishandle,
                handlepos,
                handleposfalts,
                flugelopentag,
            ),
        )

        con.commit()
        con.close()

        return OptDetailMos(
            id=new_id,
            optimized_mos_id=optimized_mos_id,
            orderid=orderid,
            itemsdetailid=itemsdetailid,
            itemlong=itemlong,
            qty=qty,
            ug1=ug1,
            ug2=ug2,
            num=num,
            subnum=subnum,
            long_al=long_al,
            izdpart=izdpart,
            partside=partside,
            modelno=modelno,
            modelheight=modelheight,
            modelwidth=modelwidth,
            flugelopentype=flugelopentype,
            flugelcount=flugelcount,
            ishandle=ishandle,
            handlepos=handlepos,
            handleposfalts=handleposfalts,
            flugelopentag=flugelopentag,
        )
    except Exception as e:
        try:
            con.rollback()
        except:
            pass
        if ENABLE_LOGGING:
            print(f"Ошибка вставки в OPTDETAIL_MOS: {e}")
        raise


def delete_grorders_mos(grorders_mos_id: int) -> bool:
    """
    Удалить запись из GRORDERS_MOS по ID. Возвращает True, если запись удалена.
    """
    try:
        con = get_db_connection()
        cur = con.cursor()

        con.begin()
        cur.execute("DELETE FROM GRORDERS_MOS WHERE ID = ?", (grorders_mos_id,))
        affected = cur.rowcount if hasattr(cur, "rowcount") else None
        con.commit()
        con.close()

        return bool(affected) if affected is not None else True
    except Exception as e:
        try:
            con.rollback()
        except:
            pass
        if ENABLE_LOGGING:
            print(f"Ошибка удаления из GRORDERS_MOS: {e}")
        raise


def delete_optimized_mos_by_grorders_mos_id(grorders_mos_id: int) -> bool:
    """
    Удалить все записи из OPTIMIZED_MOS по GRORDER_MOS_ID.
    Дополнительно удаляет связанные записи из OPTDETAIL_MOS, чтобы избежать конфликтов внешних ключей.
    Возвращает True, если удаление прошло успешно.
    """
    try:
        con = get_db_connection()
        cur = con.cursor()

        con.begin()

        # Сначала удаляем детали, связанные с optimized_mos для указанного grorders_mos_id
        cur.execute(
            """
            DELETE FROM OPTDETAIL_MOS
            WHERE OPTIMIZED_MOS_ID IN (
                SELECT OPTIMIZED_MOS_ID FROM OPTIMIZED_MOS WHERE GRORDER_MOS_ID = ?
            )
            """,
            (grorders_mos_id,),
        )

        # Затем удаляем сами optimized_mos
        cur.execute(
            "DELETE FROM OPTIMIZED_MOS WHERE GRORDER_MOS_ID = ?",
            (grorders_mos_id,),
        )
        affected = cur.rowcount if hasattr(cur, "rowcount") else None

        con.commit()
        con.close()

        return bool(affected) if affected is not None else True
    except Exception as e:
        try:
            con.rollback()
        except:
            pass
        if ENABLE_LOGGING:
            print(f"Ошибка удаления из OPTIMIZED_MOS по GRORDER_MOS_ID={grorders_mos_id}: {e}")
        raise