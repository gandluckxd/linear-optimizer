"""
Функции для работы с базой данных Altawin
"""

import fdb
import time
from modules.config import DB_CONFIG, ENABLE_LOGGING
from modules.models import Profile, Stock, MoskitkaProfile, StockRemainder, StockMaterial, GrordersMos, OptimizedMos, OptDetailMos
from modules.models import FiberglassDetail, FiberglassSheet, FiberglassLoadDataResponse
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
            itd.thick,
            o.orderid
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
                order_id=row[10],  # o.orderid - реальный ID заказа
                element_name=row[4] or "",  # oi_name - Элемент (наименование orderitem)
                profile_code=row[6],  # g_marking - Артикул профиля
                length=float(row[9]),  # thick (длина)
                quantity=int(row[8])  # total_qty - Количество
            )
            profiles.append(profile)
            print(f"🔍 DB: *** ОТЛАДКА *** Загружен профиль: goodsid={row[7]}, orderid={row[10]}, length={row[9]}, qty={row[8]}")
        
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
            NULL as warehouseremaindersid,
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
            whr.WHREMAINDERID as warehouseremaindersid,
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
                is_remainder=bool(row[5]),  # is_remainder
                warehouseremaindersid=row[6]  # warehouseremaindersid
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
            select
                g.marking as profile_code,
                whm.thick as length,
                whm.qty - whm.reserveqty as quantity_pieces
            from warehouseremainder whm
            join goods g on g.goodsid = whm.goodsid
            join groupgoods gg on gg.grgoodsid = g.grgoodsid
            where g.MARKING IN ({placeholders})
            and (whm.qty - whm.reserveqty) > 0
            ORDER BY g.MARKING, whm.THICK DESC
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
        if ENABLE_LOGGING:
            print("⚠️ get_stock_materials: Пустой список артикулов profile_codes")
        return stock_materials
    
    if ENABLE_LOGGING:
        print(f"🔧 get_stock_materials: Загрузка материалов для {len(profile_codes)} артикулов: {profile_codes}")
    
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
        
        if ENABLE_LOGGING:
            print(f"🔧 get_stock_materials: Выполняю SQL-запрос:")
            print(f"   SQL: {sql}")
            print(f"   Параметры: {profile_codes}")
        
        cur.execute(sql, profile_codes)
        rows = cur.fetchall()
        
        if ENABLE_LOGGING:
            print(f"🔧 get_stock_materials: Получено {len(rows)} строк из БД")
            for i, row in enumerate(rows):
                print(f"   Строка {i+1}: {row}")
        
        for row in rows:
            material = StockMaterial(
                profile_code=row[0],  # profile_code
                length=float(row[1]) if row[1] else 6000.0,  # length (типовой размер из gg.THICK)
                quantity_pieces=int(row[4]) if row[4] else 0  # quantity_pieces - складское количество / типовой размер
            )
            stock_materials.append(material)
            
            if ENABLE_LOGGING:
                print(f"   ✅ Создан материал: {material.profile_code}, длина={material.length}мм, количество={material.quantity_pieces}шт")
        
        con.close()
        
        if ENABLE_LOGGING:
            print(f"✅ get_stock_materials: Итого получено {len(stock_materials)} материалов со склада")
            if stock_materials:
                print(f"   Распределение по артикулам:")
                for material in stock_materials:
                    print(f"   - {material.profile_code}: {material.quantity_pieces} хлыстов по {material.length}мм")
            else:
                print("⚠️ МАТЕРИАЛЫ НЕ ЗАГРУЖЕНЫ! Запускаю диагностику...")
                diagnosis = diagnose_stock_materials_issue(profile_codes)
                print(f"📋 Результат диагностики: {diagnosis}")
            
    except Exception as e:
        if ENABLE_LOGGING:
            print(f"❌ Ошибка получения материалов: {e}")
        raise
    
    return stock_materials

def diagnose_stock_materials_issue(profile_codes: List[str]) -> Dict[str, Any]:
    """
    Диагностика проблем с загрузкой материалов со склада
    """
    diagnosis = {
        "profile_codes": profile_codes,
        "goods_found": [],
        "warehouse_data": [],
        "groupgoods_data": [],
        "thick_values": [],
        "total_warehouse_records": 0,
        "issues": []
    }
    
    if not profile_codes:
        diagnosis["issues"].append("Пустой список артикулов profile_codes")
        return diagnosis
    
    try:
        con = get_db_connection()
        cur = con.cursor()
        
        # Создаем строку для IN условия
        placeholders = ','.join(['?'] * len(profile_codes))
        
        # 1. Проверяем, есть ли товары с такими артикулами
        goods_sql = f"""
        SELECT g.GOODSID, g.MARKING, g.DELETED, gg.GRGOODSID, gg.THICK, gg.DELETED as GG_DELETED
        FROM GOODS g 
        JOIN GROUPGOODS gg ON gg.GRGOODSID = g.GRGOODSID
        WHERE g.MARKING IN ({placeholders})
        ORDER BY g.MARKING
        """
        
        cur.execute(goods_sql, profile_codes)
        goods_rows = cur.fetchall()
        
        for row in goods_rows:
            diagnosis["goods_found"].append({
                "goodsid": row[0],
                "marking": row[1], 
                "deleted": row[2],
                "grgoodsid": row[3],
                "thick": row[4],
                "gg_deleted": row[5]
            })
            diagnosis["thick_values"].append(row[4])
        
        if not goods_rows:
            diagnosis["issues"].append(f"Не найдено товаров с артикулами: {profile_codes}")
            return diagnosis
        
        # 2. Проверяем склад для найденных товаров
        goodsids = [str(row[0]) for row in goods_rows]
        warehouse_sql = f"""
        SELECT wh.GOODSID, wh.QTY, wh.RESERVEQTY, (wh.QTY - wh.RESERVEQTY) as available_qty,
               whl.DELETED as WHL_DELETED, g.MARKING
        FROM WAREHOUSE wh
        JOIN WH_LIST whl ON whl.WHLISTID = wh.WHLISTID  
        JOIN GOODS g ON g.GOODSID = wh.GOODSID
        WHERE wh.GOODSID IN ({','.join(['?'] * len(goodsids))})
        ORDER BY g.MARKING
        """
        
        cur.execute(warehouse_sql, goodsids)
        warehouse_rows = cur.fetchall()
        
        diagnosis["total_warehouse_records"] = len(warehouse_rows)
        
        for row in warehouse_rows:
            diagnosis["warehouse_data"].append({
                "goodsid": row[0],
                "qty": row[1],
                "reserve_qty": row[2], 
                "available_qty": row[3],
                "whl_deleted": row[4],
                "marking": row[5]
            })
        
        # 3. Анализ условий фильтрации
        filtered_count = 0
        available_count = 0
        thick_filtered_count = 0
        
        for wh_row in warehouse_rows:
            available_qty = wh_row[3]
            whl_deleted = wh_row[4]
            goodsid = wh_row[0]
            
            # Находим thick для этого товара
            thick = None
            for goods_row in goods_rows:
                if goods_row[0] == goodsid:
                    thick = goods_row[4]
                    break
            
            if available_qty > 0:
                available_count += 1
                
            if whl_deleted == 0 and available_qty > 0:
                filtered_count += 1
                
            if thick is not None and thick > 1:
                thick_filtered_count += 1
        
        diagnosis["available_count"] = available_count
        diagnosis["filtered_count"] = filtered_count  
        diagnosis["thick_filtered_count"] = thick_filtered_count
        
        # 4. Выявляем проблемы
        if not warehouse_rows:
            diagnosis["issues"].append("Товары не найдены на складе")
        elif available_count == 0:
            diagnosis["issues"].append("Все товары имеют нулевые остатки")
        elif filtered_count == 0:
            diagnosis["issues"].append("Все записи отфильтрованы условиями (whl.DELETED=0 или qty<=0)")
        elif thick_filtered_count == 0:
            diagnosis["issues"].append("Все товары отфильтрованы условием gg.THICK > 1")
            
        con.close()
        
        if ENABLE_LOGGING:
            print(f"🔧 Диагностика материалов:")
            print(f"   Артикулы: {profile_codes}")
            print(f"   Найдено товаров: {len(goods_rows)}")
            print(f"   Записей на складе: {len(warehouse_rows)}")
            print(f"   С доступными остатками: {available_count}")
            print(f"   Прошли фильтрацию: {filtered_count}")
            print(f"   С thick > 1: {thick_filtered_count}")
            print(f"   Значения thick: {diagnosis['thick_values']}")
            if diagnosis["issues"]:
                print(f"   Проблемы: {diagnosis['issues']}")
                
    except Exception as e:
        diagnosis["issues"].append(f"Ошибка диагностики: {e}")
        if ENABLE_LOGGING:
            print(f"❌ Ошибка диагностики: {e}")
    
    return diagnosis


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
        except Exception:
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
    Обогатить поля OPTDETAIL_MOS на основании данных из БД.
    Возвращает словарь с правильным orderid и обогащенными полями.
    
    ВАЖНО: Функция корректно определяет orderid по itemsdetailid если он найден,
    иначе использует переданный orderid.
    """
    try:
        if ENABLE_LOGGING:
            print(f"🔧 DB: *** ИСПРАВЛЕННАЯ ВЕРСИЯ *** Обогащение полей OPTDETAIL_MOS для optimized_mos_id={optimized_mos_id}, orderid={orderid}")
        
        con = get_db_connection()
        cur = con.cursor()

        # Узнаем GOODSID по текущему OPTIMIZED_MOS
        goods_id_for_bar = None
        grorders_mos_id = None
        try:
            cur.execute(
                "SELECT GOODSID, GRORDER_MOS_ID FROM OPTIMIZED_MOS WHERE OPTIMIZED_MOS_ID = ?",
                (optimized_mos_id,),
            )
            row_goods = cur.fetchone()
            goods_id_for_bar = int(row_goods[0]) if row_goods and row_goods[0] is not None else None
            grorders_mos_id = int(row_goods[1]) if row_goods and row_goods[1] is not None else None
            
            if ENABLE_LOGGING:
                print(f"🔧 DB: Найден GOODSID={goods_id_for_bar}, GRORDER_MOS_ID={grorders_mos_id}")
                
        except Exception as e:
            if ENABLE_LOGGING:
                print(f"⚠️ DB: Не удалось получить GOODSID для optimized_mos_id={optimized_mos_id}: {e}")
            goods_id_for_bar = None
            grorders_mos_id = None

        # Определяем корректный orderid
        final_orderid = orderid  # По умолчанию используем переданный
        
        # 1) Сначала ищем ITEMSDETAIL для обогащения полей
        try:
            if itemsdetailid is None and orderid and goods_id_for_bar:
                target_length = float(itemlong or 0)
                if ENABLE_LOGGING:
                    print(f"🔧 DB: *** НОВАЯ ЛОГИКА *** Поиск ITEMSDETAIL по ORDERID={orderid}, GOODSID={goods_id_for_bar}, длина={target_length}")
                
                # Ищем ITEMSDETAIL по ORDERID и GOODSID
                cur.execute(
                    (
                        "SELECT FIRST 1 itd.ITEMSDETAILID, itd.ANG1, itd.ANG2, itd.IZDPART, itd.PARTSIDE, "
                        "itd.MODELNO, oi.WIDTH AS O_WIDTH, oi.HEIGHT AS O_HEIGHT, itd.WIDTH AS D_WIDTH, itd.HEIGHT AS D_HEIGHT, itd.THICK "
                        "FROM ITEMSDETAIL itd "
                        "JOIN ORDERITEMS oi ON oi.ORDERITEMSID = itd.ORDERITEMSID "
                        "WHERE oi.ORDERID = ? AND itd.GOODSID = ? "
                        "ORDER BY ABS(COALESCE(itd.THICK, 0) - ?) ASC, itd.ITEMSDETAILID DESC"
                    ),
                    (int(orderid), goods_id_for_bar, target_length),
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
                    
                    if ENABLE_LOGGING:
                        print(f"✅ DB: Найден ITEMSDETAIL по ORDERID и GOODSID: id={itemsdetailid}")

                # Резервный поиск только по ORDERID и длине
                if itemsdetailid is None and itemlong is not None:
                    if ENABLE_LOGGING:
                        print(f"🔧 DB: Резервный поиск ITEMSDETAIL только по ORDERID={orderid} и длине={itemlong}")
                    
                    cur.execute(
                        (
                            "SELECT FIRST 1 itd.ITEMSDETAILID FROM ITEMSDETAIL itd "
                            "JOIN ORDERITEMS oi ON oi.ORDERITEMSID = itd.ORDERITEMSID "
                            "WHERE oi.ORDERID = ? "
                            "ORDER BY ABS(COALESCE(itd.THICK, 0) - ?) ASC, itd.ITEMSDETAILID DESC"
                        ),
                        (int(orderid), float(itemlong)),
                    )
                    cand_simple = cur.fetchone()
                    if cand_simple:
                        itemsdetailid = int(cand_simple[0])
                        if ENABLE_LOGGING:
                            print(f"✅ DB: Найден ITEMSDETAIL резервным поиском: id={itemsdetailid}")

        except Exception as e:
            if ENABLE_LOGGING:
                print(f"⚠️ DB: Ошибка поиска ITEMSDETAIL: {e}")

        # 2) КЛЮЧЕВАЯ ЛОГИКА: Определяем корректный orderid по itemsdetailid
        if itemsdetailid:
            correct_orderid = get_orderid_by_itemsdetailid(itemsdetailid)
            if correct_orderid:
                final_orderid = correct_orderid
                if ENABLE_LOGGING:
                    print(f"✅ DB: *** ИСПРАВЛЕНО *** Корректный orderid определен по itemsdetailid={itemsdetailid}: {final_orderid}")
            else:
                if ENABLE_LOGGING:
                    print(f"⚠️ DB: Не удалось определить orderid по itemsdetailid={itemsdetailid}, используем переданный: {final_orderid}")
        else:
            if ENABLE_LOGGING:
                print(f"⚠️ DB: itemsdetailid не найден, используем переданный orderid: {final_orderid}")

        # 2) Если не нашли ITEMSDETAIL, пробуем заполнить поля по умолчанию
        if itemsdetailid is None:
            if ENABLE_LOGGING:
                print(f"🔧 DB: ITEMSDETAIL не найден, используем значения по умолчанию")
            
            # Пытаемся получить информацию о профиле по goods_id_for_bar
            if goods_id_for_bar:
                try:
                    cur.execute(
                        "SELECT FIRST 1 g.marking, gg.thick FROM goods g JOIN groupgoods gg ON gg.grgoodsid = g.grgoodsid WHERE g.goodsid = ?",
                        (goods_id_for_bar,)
                    )
                    profile_info = cur.fetchone()
                    if profile_info:
                        marking = profile_info[0]
                        thick = profile_info[1]
                        if ENABLE_LOGGING:
                            print(f"🔧 DB: Найден профиль: marking={marking}, thick={thick}")
                        
                        # Устанавливаем значения по умолчанию на основе профиля
                        if modelwidth is None:
                            modelwidth = int(thick) if thick else None
                        if modelheight is None:
                            modelheight = int(thick) if thick else None
                except Exception as e:
                    if ENABLE_LOGGING:
                        print(f"⚠️ DB: Не удалось получить информацию о профиле: {e}")

        con.close()

        # Формируем результат с корректным orderid
        result = {
            "orderid": final_orderid,  # *** ИСПРАВЛЕНО *** Возвращаем корректный orderid
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
        
        if ENABLE_LOGGING:
            print(f"✅ DB: *** ИСПРАВЛЕНО *** Обогащение полей завершено: orderid={final_orderid}, itemsdetailid={itemsdetailid}, modelwidth={modelwidth}, modelheight={modelheight}")
        
        return result

    except Exception as e:
        if ENABLE_LOGGING:
            print(f"❌ DB: Ошибка обогащения полей: {e}")
        # Возвращаем исходные значения в случае ошибки
        return {
            "orderid": orderid,  # В случае ошибки используем исходный orderid
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
    except Exception:
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
        except Exception:
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
            warehouseremaindersid=None,  # Это поле не существует в таблице
        )
    except Exception as e:
        try:
            con.rollback()
        except Exception:
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
    
    ВАЖНО: orderid должен быть корректным ORDERID из таблицы ORDERS,
    а не GRORDERID. Правильный orderid определяется из результатов оптимизации.
    """
    print(f"🔍 DB FUNCTION: *** ИСПРАВЛЕННАЯ ВЕРСИЯ *** insert_optdetail_mos вызвана с orderid={orderid}")
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
        except Exception:
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
        except Exception:
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
        except Exception:
            pass
        if ENABLE_LOGGING:
            print(f"Ошибка удаления из OPTIMIZED_MOS по GRORDER_MOS_ID={grorders_mos_id}: {e}")
        raise


def adjust_materials_for_moskitka_optimization(grorders_mos_id: int, used_materials: list = None, business_remainders: list = None) -> dict:
    """
    Скорректировать списание и приход материалов в Altawin для оптимизации москитных сеток.
    
    Args:
        grorders_mos_id: ID сменного задания москитных сеток
        used_materials: Список использованных материалов [{'goodsid': int, 'length': float, 'quantity': int, 'is_remainder': bool}]
        business_remainders: Список деловых остатков [{'goodsid': int, 'length': float, 'quantity': int}]
        
    Returns:
        dict: Результат операции
    """
    operation_start_time = time.time()
    
    try:
        print(f"🔧 DB: Начало корректировки материалов для москитных сеток grorders_mos_id={grorders_mos_id}")
        print(f"🔧 DB: Получены параметры:")
        print(f"   used_materials: {len(used_materials) if used_materials else 0} записей")
        print(f"   business_remainders: {len(business_remainders) if business_remainders else 0} записей")
        
        if used_materials:
            print(f"🔧 DB: Детализация used_materials:")
            for i, material in enumerate(used_materials):
                print(f"   [{i}] goodsid={material.get('goodsid')}, length={material.get('length')}, quantity={material.get('quantity')}, is_remainder={material.get('is_remainder')}")
        
        if business_remainders:
            print(f"🔧 DB: Детализация business_remainders:")
            for i, remainder in enumerate(business_remainders):
                print(f"   [{i}] goodsid={remainder.get('goodsid')}, length={remainder.get('length')}, quantity={remainder.get('quantity')}")
        
        con = get_db_connection()
        cur = con.cursor()
        
        # 1. Получаем все связанные grorderid по grorders_mos_id
        grorder_ids = get_grorder_ids_by_grorders_mos_id(grorders_mos_id)
        if not grorder_ids:
            return {
                "success": False,
                "error": f"Не найдено связанных сменных заданий для grorders_mos_id={grorders_mos_id}"
            }
        
        print(f"🔧 DB: Найдено {len(grorder_ids)} связанных сменных заданий: {grorder_ids}")
        
        # 2. Удаляем материалы типа "профили москитной сетки" из всех списаний
        print(f"🔧 DB: Удаление материалов типа 'профили москитной сетки' из списаний...")
        deleted_outlay_count = 0
        
        for grorder_id in grorder_ids:
            # Ищем списание для текущего grorder
            outlay_sql = """
            SELECT outlayid FROM outlay 
            WHERE grorderid = ? AND deleted = 0
            ORDER BY outlayid
            """
            cur.execute(outlay_sql, (grorder_id,))
            outlay_result = cur.fetchone()
            
            if outlay_result:
                outlay_id = outlay_result[0]
                print(f"🔧 DB: Обрабатываем списание outlayid={outlay_id} для grorderid={grorder_id}")
                
                # Удаляем элементы списания с профилями москитных сеток (ggtypeid = 48)
                delete_outlay_detail_sql = """
                DELETE FROM outlaydetail WHERE outlaydetailid IN (
                    SELECT ot.outlaydetailid
                    FROM outlaydetail ot
                    JOIN goods g ON g.goodsid = ot.goodsid
                    JOIN groupgoods gg ON gg.grgoodsid = g.grgoodsid
                    WHERE ot.outlayid = ? AND gg.ggtypeid = 48
                )
                """
                cur.execute(delete_outlay_detail_sql, (outlay_id,))
                deleted_details = cur.rowcount
                deleted_outlay_count += deleted_details
                print(f"🔧 DB: Удалено {deleted_details} элементов списания профилей москитных сеток")
                
                # Удаляем остатки из списания с профилями москитных сеток
                delete_outlay_remainder_sql = """
                DELETE FROM outlayremainder WHERE outlayremainderid IN (
                    SELECT otr.outlayremainderid
                    FROM outlayremainder otr
                    JOIN goods g ON g.goodsid = otr.goodsid
                    JOIN groupgoods gg ON gg.grgoodsid = g.grgoodsid
                    WHERE otr.outlayid = ? AND gg.ggtypeid = 48
                )
                """
                cur.execute(delete_outlay_remainder_sql, (outlay_id,))
                deleted_remainders = cur.rowcount
                deleted_outlay_count += deleted_remainders
                print(f"🔧 DB: Удалено {deleted_remainders} остатков профилей москитных сеток из списания")
        
        print(f"🔧 DB: Всего удалено {deleted_outlay_count} записей из списаний")
        
        # Коммитим удаление данных из списаний
        con.commit()
        print(f"🔧 DB: Зафиксированы изменения после удаления данных из списаний")
        
        # 3. Удаляем материалы типа "профили москитной сетки" из всех приходов
        print(f"🔧 DB: Удаление материалов типа 'профили москитной сетки' из приходов...")
        deleted_supply_count = 0
        
        for grorder_id in grorder_ids:
            # Ищем приход для текущего grorder
            supply_sql = """
            SELECT supplyid FROM supply 
            WHERE grorderid = ? AND supplytype = 1 AND deleted = 0
            ORDER BY supplyid
            """
            cur.execute(supply_sql, (grorder_id,))
            supply_result = cur.fetchone()
            
            if supply_result:
                supply_id = supply_result[0]
                print(f"🔧 DB: Обрабатываем приход supplyid={supply_id} для grorderid={grorder_id}")
                
                # Удаляем элементы прихода с профилями москитных сеток
                delete_supply_detail_sql = """
                DELETE FROM supplydetail WHERE supplydetailid IN (
                    SELECT sd.supplydetailid
                    FROM supplydetail sd
                    JOIN goods g ON g.goodsid = sd.goodsid
                    JOIN groupgoods gg ON gg.grgoodsid = g.grgoodsid
                    WHERE sd.supplyid = ? AND gg.ggtypeid = 48
                )
                """
                cur.execute(delete_supply_detail_sql, (supply_id,))
                deleted_details = cur.rowcount
                deleted_supply_count += deleted_details
                print(f"🔧 DB: Удалено {deleted_details} элементов прихода профилей москитных сеток")
                
                # Удаляем остатки из прихода с профилями москитных сеток
                delete_supply_remainder_sql = """
                DELETE FROM supplyremainder WHERE supplyremainderid IN (
                    SELECT sr.supplyremainderid
                    FROM supplyremainder sr
                    JOIN goods g ON g.goodsid = sr.goodsid
                    JOIN groupgoods gg ON gg.grgoodsid = g.grgoodsid
                    WHERE sr.supplyid = ? AND gg.ggtypeid = 48
                )
                """
                cur.execute(delete_supply_remainder_sql, (supply_id,))
                deleted_remainders = cur.rowcount
                deleted_supply_count += deleted_remainders
                print(f"🔧 DB: Удалено {deleted_remainders} остатков профилей москитных сеток из прихода")
        
        print(f"🔧 DB: Всего удалено {deleted_supply_count} записей из приходов")
        
        # Коммитим удаление данных из приходов
        con.commit()
        print(f"🔧 DB: Зафиксированы изменения после удаления данных из приходов")
        
        # 4. Создаем новое списание материалов для всех grorder
        print(f"🔧 DB: Создание нового списания материалов...")
        
        # Получаем информацию о сменном задании москитных сеток для комментария
        grorder_mos_sql = "SELECT name FROM grorders_mos WHERE id = ?"
        cur.execute(grorder_mos_sql, (grorders_mos_id,))
        grorder_mos_result = cur.fetchone()
        grorder_mos_name = grorder_mos_result[0] if grorder_mos_result else f"Москитные сетки {grorders_mos_id}"
        
        # Создаем одно списание для всех grorder
        # Получаем новый GUID
        guid_sql = "SELECT guidhi, guidlo, guid FROM new_guid"
        cur.execute(guid_sql)
        guid_result = cur.fetchone()
        guidhi, guidlo, guid = guid_result
        
        # Генерируем номер накладной
        waybill = f"{grorders_mos_id}/{grorder_mos_name}"
        
        # Создаем списание
        create_outlay_sql = """
        INSERT INTO OUTLAY (
            OUTLAYID, WAYBILL, OUTLAYDATE, CUSTOMERID, OUTLAYTYPE, 
            GRORDERID, PARENTID, ISAPPROVED, RCOMMENT, WHLISTID, 
            RECCOLOR, RECFLAG, GUIDHI, GUIDLO, OWNERID, 
            DELETED, DATECREATED, DATEMODIFIED, DATEDELETED, JOBTASKID, GUID
        ) VALUES (
            gen_id(gen_outlay, 1), ?, CURRENT_DATE, NULL, 1, 
            NULL, NULL, 0, ?, 0, 
            NULL, NULL, ?, ?, 0, 
            0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL, NULL, ?
        )
        """
        comment = f"Списание материалов для оптимизации москитных сеток: {grorder_mos_name}"
        cur.execute(create_outlay_sql, (waybill, comment, guidhi, guidlo, guid))
        
        # Получаем ID созданного списания
        outlay_id_sql = "SELECT gen_id(gen_outlay, 0) FROM rdb$database"
        cur.execute(outlay_id_sql)
        outlay_id = cur.fetchone()[0]
        print(f"🔧 DB: Создано новое списание outlayid={outlay_id}")
        
        # 5. Создаем новый приход материалов для деловых остатков
        print(f"🔧 DB: Создание нового прихода материалов...")
        
        # Создаем приход
        create_supply_sql = """
        INSERT INTO SUPPLY (
            SUPPLYID, WAYBILL, SUPPLYDATE, SUPPLIERID, SUPPLYTYPE, 
            GRORDERID, PARENTID, ISAPPROVED, RCOMMENT, WHLISTID, 
            RECCOLOR, RECFLAG, GUIDHI, GUIDLO, OWNERID, 
            DELETED, DATECREATED, DATEMODIFIED, DATEDELETED, JOBTASKID, GUID
        ) VALUES (
            gen_id(gen_supply, 1), ?, CURRENT_DATE, NULL, 1, 
            NULL, NULL, 0, ?, 0, 
            NULL, NULL, ?, ?, 0, 
            0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL, NULL, ?
        )
        """
        supply_comment = f"Приход деловых остатков от оптимизации москитных сеток: {grorder_mos_name}"
        cur.execute(create_supply_sql, (grorder_mos_name, supply_comment, guidhi, guidlo, guid))
        
        # Получаем ID созданного прихода
        supply_id_sql = "SELECT gen_id(gen_supply, 0) FROM rdb$database"
        cur.execute(supply_id_sql)
        supply_id = cur.fetchone()[0]
        print(f"🔧 DB: Создан новый приход supplyid={supply_id}")
        
        # 6. Заполняем созданные документы материалами
        print(f"🔧 DB: Заполнение документов материалами...")
        
        # Заполняем списание использованными материалами
        if used_materials:
            print(f"🔧 DB: Добавление {len(used_materials)} использованных материалов в списание...")
            
            for material in used_materials:
                goodsid = material.get('goodsid')
                length = material.get('length', 0)
                quantity = material.get('quantity', 0)
                is_remainder = material.get('is_remainder', False)
                
                if not goodsid or quantity <= 0:
                    continue
                
                if is_remainder:
                    # Это деловой остаток - добавляем в OUTLAYREMAINDER
                    # Для деловых остатков количество остается в штуках
                    print(f"🔧 DB: Обрабатываем деловой остаток: goodsid={goodsid}, length={length}, quantity={quantity}, is_remainder={is_remainder}")
                    
                    insert_outlay_remainder_sql = """
                    INSERT INTO OUTLAYREMAINDER (
                        OUTLAYREMAINDERID, OUTLAYID, GOODSID, ISAPPROVED, 
                        THICK, WIDTH, HEIGHT, QTY, SELLERPRICE, SELLERCURRENCYID
                    ) VALUES (
                        gen_id(gen_outlayremainder, 1), ?, ?, 0, 
                        ?, 0, 0, ?, 0, 1
                    )
                    """
                    print(f"🔧 DB: Выполняем SQL: INSERT INTO OUTLAYREMAINDER с параметрами: outlay_id={outlay_id}, goodsid={goodsid}, length={int(length)}, quantity={quantity}")
                    cur.execute(insert_outlay_remainder_sql, (outlay_id, goodsid, int(length), quantity))
                    print(f"🔧 DB: ✅ Добавлен использованный деловой остаток в OUTLAYREMAINDER goodsid={goodsid}, длина={length}, количество={quantity}шт")
                else:
                    # Это основной материал - добавляем в OUTLAYDETAIL
                    # Получаем measureid для товара
                    measure_sql = """
                    SELECT ggm.measureid FROM goods g
                    JOIN groupgoods gg ON gg.grgoodsid = g.grgoodsid
                    JOIN grgoodsmeasure ggm ON ggm.grgoodsid = gg.grgoodsid
                    WHERE g.goodsid = ? AND ggm.ismain = 1
                    """
                    cur.execute(measure_sql, (goodsid,))
                    measure_result = cur.fetchone()
                    measureid = measure_result[0] if measure_result else 1  # По умолчанию 1
                    
                    # Получаем thick из groupgoods для правильного расчета количества
                    thick_sql = """
                    SELECT gg.thick FROM goods g
                    JOIN groupgoods gg ON gg.grgoodsid = g.grgoodsid
                    WHERE g.goodsid = ?
                    """
                    cur.execute(thick_sql, (goodsid,))
                    thick_result = cur.fetchone()
                    thick = thick_result[0] if thick_result else 6000  # По умолчанию 6000 мм
                    
                    # Рассчитываем правильное количество: количество хлыстов * thick
                    correct_quantity = quantity * thick
                    
                    insert_outlay_detail_sql = """
                    INSERT INTO OUTLAYDETAIL (
                        OUTLAYDETAILID, OUTLAYID, GOODSID, QTY, MEASUREID, 
                        ISAPPROVED, SELLERPRICE, SELLERCURRENCYID
                    ) VALUES (
                        gen_id(gen_outlaydetail, 1), ?, ?, ?, ?, 
                        0, 0, 1
                    )
                    """
                    cur.execute(insert_outlay_detail_sql, (outlay_id, goodsid, correct_quantity, measureid))
                    print(f"🔧 DB: Добавлен использованный материал goodsid={goodsid}, количество={quantity}шт * {thick}мм = {correct_quantity}мм в outlaydetail")
        
        # Заполняем приход деловыми остатками
        if business_remainders:
            print(f"🔧 DB: Добавление {len(business_remainders)} деловых остатков в приход...")
            
            for remainder in business_remainders:
                goodsid = remainder.get('goodsid')
                length = remainder.get('length', 0)
                quantity = remainder.get('quantity', 0)
                
                if not goodsid or quantity <= 0 or length <= 0:
                    continue
                
                # Получаем стоимость товара
                price_sql = """
                SELECT COALESCE(g.price1, 0) as price
                FROM goods g 
                WHERE g.goodsid = ?
                """
                cur.execute(price_sql, (goodsid,))
                price_result = cur.fetchone()
                price = price_result[0] if price_result else 0
                
                # Получаем thick из groupgoods для правильного расчета количества
                thick_sql = """
                SELECT gg.thick FROM goods g
                JOIN groupgoods gg ON gg.grgoodsid = g.grgoodsid
                WHERE g.goodsid = ?
                """
                cur.execute(thick_sql, (goodsid,))
                thick_result = cur.fetchone()
                thick = thick_result[0] if thick_result else 6000  # По умолчанию 6000 мм
                
                # Рассчитываем правильное количество: количество хлыстов * thick
                correct_quantity = quantity * thick
                
                # Добавляем деловой остаток в приход (SUPPLYREMAINDER)
                insert_supply_remainder_sql = """
                INSERT INTO SUPPLYREMAINDER (
                    SUPPLYREMAINDERID, SUPPLYID, GOODSID, ISAPPROVED, 
                    THICK, WIDTH, HEIGHT, QTY, SELLERPRICE, SELLERCURRENCYID
                ) VALUES (
                    gen_id(gen_supplyremainder, 1), ?, ?, 0, 
                    ?, 0, 0, ?, ?, 1
                )
                """
                cur.execute(insert_supply_remainder_sql, (supply_id, goodsid, int(length), correct_quantity, price))
                print(f"🔧 DB: Добавлен деловой остаток в SUPPLYREMAINDER goodsid={goodsid}, длина={length}, количество={quantity}шт * {thick}мм = {correct_quantity}мм")
                

        
        # Фиксируем изменения
        con.commit()
        con.close()
        
        total_time = time.time() - operation_start_time
        print(f"✅ DB: Корректировка материалов завершена успешно за {total_time:.2f} секунд")
        
        return {
            "success": True,
            "message": "Материалы успешно скорректированы",
            "outlay_id": outlay_id,
            "supply_id": supply_id,
            "deleted_outlay_count": deleted_outlay_count,
            "deleted_supply_count": deleted_supply_count,
            "grorder_ids": grorder_ids,
            "performance": {
                "total_time": round(total_time, 2)
            }
        }
        
    except Exception as e:
        total_time = time.time() - operation_start_time
        print(f"❌ DB: Ошибка корректировки материалов за {total_time:.2f}с: {e}")
        import traceback
        print(f"❌ DB: Трассировка ошибки: {traceback.format_exc()}")
        
        # Пытаемся откатить изменения в случае ошибки
        try:
            if 'con' in locals() and con:
                con.rollback()
                print(f"🔄 DB: Выполнен откат транзакции")
                con.close()
        except Exception as rollback_error:
            print(f"❌ DB: Ошибка при откате транзакции: {rollback_error}")
        
        try:
            if 'con' in locals() and not con.closed:
                con.rollback()
                con.close()
        except Exception:
            pass
            
        return {
            "success": False,
            "error": str(e),
            "performance": {
                "total_time": round(total_time, 2)
            }
        }

def get_orderid_by_itemsdetailid(itemsdetailid: int) -> int | None:
    """
    Получить корректный ORDERID по ITEMSDETAILID
    
    Args:
        itemsdetailid: ID детали конструкции
        
    Returns:
        ORDERID из таблицы ORDERS или None если не найден
    """
    try:
        con = get_db_connection()
        cur = con.cursor()
        
        sql = """
        SELECT oi.orderid
        FROM itemsdetail itd
        JOIN orderitems oi ON oi.orderitemsid = itd.orderitemsid
        WHERE itd.itemsdetailid = ?
        """
        
        if ENABLE_LOGGING:
            print(f"🔧 DB: Получение orderid для itemsdetailid={itemsdetailid}")
        
        cur.execute(sql, (itemsdetailid,))
        result = cur.fetchone()
        con.close()
        
        if result:
            orderid = int(result[0])
            if ENABLE_LOGGING:
                print(f"✅ DB: Найден orderid={orderid} для itemsdetailid={itemsdetailid}")
            return orderid
        else:
            if ENABLE_LOGGING:
                print(f"⚠️ DB: Не найден orderid для itemsdetailid={itemsdetailid}")
            return None
            
    except Exception as e:
        if ENABLE_LOGGING:
            print(f"❌ DB: Ошибка получения orderid для itemsdetailid={itemsdetailid}: {e}")
        return None

def get_warehouse_remainders_by_goodsid(goodsid: int) -> List[Dict[str, Any]]:
    """
    Получить деловые остатки со склада по goodsid
    Использует SQL запрос, указанный пользователем
    """
    try:
        con = get_db_connection()
        cur = con.cursor()
        
        sql = """
        SELECT
            g.marking AS g_marking,
            whm.goodsid,
            whm.thick,
            whm.qty - whm.reserveqty AS qty
        FROM warehouseremainder whm
        JOIN goods g ON g.goodsid = whm.goodsid
        JOIN groupgoods gg ON gg.grgoodsid = g.grgoodsid
        JOIN measure m ON m.measureid = gg.measureid
        WHERE whm.goodsid = ?
        """
        
        cur.execute(sql, (goodsid,))
        rows = cur.fetchall()
        
        remainders = []
        for row in rows:
            remainder = {
                'marking': row[0],  # g_marking
                'goodsid': row[1],  # goodsid
                'thick': row[2],    # thick
                'qty': row[3]       # qty
            }
            remainders.append(remainder)
        
        con.close()
        
        if ENABLE_LOGGING:
            print(f"✅ Получено {len(remainders)} деловых остатков для goodsid {goodsid}")
            
        return remainders
        
    except Exception as e:
        if ENABLE_LOGGING:
            print(f"❌ Ошибка получения деловых остатков: {e}")
        raise


def distribute_cell_numbers(grorder_mos_id: int) -> Dict[str, Any]:
    """
    Распределение ячеек для оптимизации москитных сеток.
    Выполняется ПОСЛЕ загрузки данных оптимизации в altawin.
    
    Логика:
    1. Получаем все уникальные orderitemsid с маркировкой проема по grorder_mos_id
    2. Проходим циклом for по результатам и присваиваем каждому уникальному проему последовательный номер ячейки
    3. Обновляем поле cell_number в таблице optdetail_mos
    
    Args:
        grorder_mos_id: ID сменного задания москитных сеток
        
    Returns:
        dict: Результат операции с информацией о количестве обработанных проемов
    """
    operation_start_time = time.time()
    
    try:
        if ENABLE_LOGGING:
            print(f"🔧 DB: Начало распределения ячеек для grorder_mos_id={grorder_mos_id}")
        
        con = get_db_connection()
        cur = con.cursor()
        
        # Начинаем транзакцию
        con.begin()
        
        # 1. Получаем все уникальные orderitemsid с маркировкой проема
        unique_items_sql = """
        SELECT DISTINCT
            vd.partside,
            vd.orderitemsid
        FROM voptdetail_mos vd
        WHERE vd.optimizedid IN (
            SELECT om.optimized_mos_id 
            FROM optimized_mos om 
            WHERE om.grorder_mos_id = ?
        )
        ORDER BY vd.orderitemsid, vd.partside
        """
        
        if ENABLE_LOGGING:
            print("🔧 DB: Выполняем SQL-запрос для получения уникальных проемов:")
            print(f"   SQL: {unique_items_sql}")
            print(f"   Параметр: grorder_mos_id={grorder_mos_id}")
        
        cur.execute(unique_items_sql, (grorder_mos_id,))
        unique_items = cur.fetchall()
        
        if not unique_items:
            if ENABLE_LOGGING:
                print(f"⚠️ DB: Не найдено уникальных проемов для grorder_mos_id={grorder_mos_id}")
            con.rollback()
            con.close()
            return {
                "success": False,
                "message": "Не найдено уникальных проемов для распределения ячеек",
                "processed_items": 0,
                "performance": {
                    "total_time": round(time.time() - operation_start_time, 2)
                }
            }
        
        if ENABLE_LOGGING:
            print(f"✅ DB: Найдено {len(unique_items)} уникальных проемов для распределения ячеек")
            for i, item in enumerate(unique_items):
                print(f"   [{i+1}] partside='{item[0]}', orderitemsid={item[1]}")
        
        # 2. Проходим циклом for и присваиваем номера ячеек (начинаем с 1)
        processed_count = 0
        
        for i, (partside, orderitemsid) in enumerate(unique_items, start=1):  # Начинаем с 1
            if ENABLE_LOGGING:
                print(f"🔧 DB: Обрабатываем проем {i}/{len(unique_items)}: partside='{partside}', orderitemsid={orderitemsid}")
            
            # 3. Обновляем номер ячейки для всех записей данного проема
            update_cell_sql = """
            UPDATE optdetail_mos odm 
            SET odm.cell_number = ? 
            WHERE (odm.itemsdetailid IN (
                SELECT itd.itemsdetailid 
                FROM itemsdetail itd 
                WHERE itd.orderitemsid = ?
            ))
            AND (odm.partside = ?)
            """
            
            if ENABLE_LOGGING:
                print(f"🔧 DB: Выполняем UPDATE с параметрами: cell_number={i}, orderitemsid={orderitemsid}, partside='{partside}'")
            
            cur.execute(update_cell_sql, (i, orderitemsid, partside))
            updated_rows = cur.rowcount if hasattr(cur, 'rowcount') else 0
            
            if ENABLE_LOGGING:
                print(f"✅ DB: Обновлено {updated_rows} записей для проема с cell_number={i}")
            
            processed_count += 1
        
        # Фиксируем изменения
        con.commit()
        con.close()
        
        total_time = time.time() - operation_start_time
        
        if ENABLE_LOGGING:
            print(f"✅ DB: Распределение ячеек завершено успешно за {total_time:.2f} секунд")
            print(f"   Обработано уникальных проемов: {processed_count}")
        
        return {
            "success": True,
            "message": f"Распределение ячеек выполнено успешно для {processed_count} уникальных проемов",
            "processed_items": processed_count,
            "grorder_mos_id": grorder_mos_id,
            "performance": {
                "total_time": round(total_time, 2)
            }
        }
        
    except Exception as e:
        total_time = time.time() - operation_start_time
        
        if ENABLE_LOGGING:
            print(f"❌ DB: Ошибка распределения ячеек за {total_time:.2f}с: {e}")
            import traceback
            print(f"❌ DB: Трассировка ошибки: {traceback.format_exc()}")
        
        # Откатываем изменения в случае ошибки
        try:
            if 'con' in locals() and con:
                con.rollback()
                print("🔄 DB: Выполнен откат транзакции")
                con.close()
        except Exception as rollback_error:
            print(f"❌ DB: Ошибка при откате транзакции: {rollback_error}")
        
        return {
            "success": False,
            "error": str(e),
            "processed_items": 0,
            "performance": {
                "total_time": round(total_time, 2)
            }
        }

# ========================================
# НОВЫЕ МЕТОДЫ ДЛЯ ФИБЕРГЛАССА
# ========================================

def get_fiberglass_details_by_grorder_mos_id(grorder_mos_id: int) -> List[FiberglassDetail]:
    """
    Получить детали фибергласса по grorder_mos_id
    Адаптировано на основе запросов профилей с учетом плоскостного материала (фибергласс)
    """
    details = []

    try:
        con = get_db_connection()
        cur = con.cursor()

        # SQL запрос адаптированный из запросов профилей для фибергласса
        # Используем фильтр gg.ggtypeid = 58 для типа материала "фибергласс"
        sql = f"""
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
            itd.width as detail_width,
            itd.height as detail_height,
            itd.thick,
            o.orderid,
            itd.itemsdetailid,
            od.modelno,
            od.partside,
            od.izdpart
        FROM grorders gr
        JOIN grorder_uf_values guv ON gr.grorderid = guv.grorderid
        JOIN grordersdetail grd ON grd.grorderid = gr.grorderid
        JOIN orderitems oi ON oi.orderitemsid = grd.orderitemsid
        JOIN orders o ON o.orderid = oi.orderid
        JOIN itemsdetail itd ON itd.orderitemsid = oi.orderitemsid
        JOIN goods g ON g.goodsid = itd.goodsid
        JOIN groupgoods gg ON gg.grgoodsid = itd.grgoodsid
        JOIN groupgoodstypes ggt ON ggt.ggtypeid = gg.ggtypeid
        LEFT JOIN optdetail_mos od ON oi.orderid = od.orderid AND itd.itemsdetailid = od.itemsdetailid
        WHERE guv.userfieldid = 8
        AND guv.var_str = '{grorder_mos_id}'
        AND gg.ggtypeid = 58
        ORDER BY oi.orderitemsid
        """

        if ENABLE_LOGGING:
            print(f"🔍 DB: Выполняем запрос для grorder_mos_id={grorder_mos_id}")
            print(f"🔍 DB: SQL: {sql}")

        cur.execute(sql)
        rows = cur.fetchall()

        for row in rows:
            detail = FiberglassDetail(
                grorder_mos_id=grorder_mos_id,
                orderid=int(row[12]) if row[12] else 0,  # o.orderid
                orderitemsid=int(row[3]) if row[3] else 0,  # oi.orderitemsid
                itemsdetailid=int(row[13]) if row[13] else 0,  # itd.itemsdetailid
                item_name=str(row[4]) if row[4] else "",  # oi.name
                width=float(row[9]) if row[9] else 0.0,  # itd.width
                height=float(row[10]) if row[10] else 0.0,  # itd.height
                quantity=int(row[8]) if row[8] else 0,  # total_qty
                modelno=int(row[14]) if row[14] else None,  # od.modelno
                partside=str(row[15]) if row[15] else None,  # od.partside
                izdpart=str(row[16]) if row[16] else None,  # od.izdpart
                goodsid=int(row[7]) if row[7] else 0,  # g.goodsid
                marking=str(row[6]) if row[6] else ""  # g.marking
            )
            details.append(detail)

            if ENABLE_LOGGING:
                print(f"🔍 DB: Загружена деталь фибергласса: {detail.marking}, размер {detail.width}x{detail.height}мм, кол-во {detail.quantity}")

        con.close()

    except Exception as e:
        if ENABLE_LOGGING:
            print(f"❌ Ошибка получения деталей фибергласса: {e}")
        raise

    if ENABLE_LOGGING:
        print(f"✅ Получено {len(details)} деталей фибергласса для grorder_mos_id={grorder_mos_id}")

    return details

def get_fiberglass_warehouse_materials(goodsids: List[int]) -> List[FiberglassSheet]:
    """
    Получить цельные рулоны фибергласса со склада
    Количество рулонов рассчитывается как: общее_количество / (ширина * высота)
    Адаптировано на основе запросов профилей для плоскостного материала
    """
    materials = []

    if not goodsids:
        if ENABLE_LOGGING:
            print("⚠️ DB: goodsids пустой, пропускаем запрос материалов")
        return materials

    try:
        con = get_db_connection()
        cur = con.cursor()

        # Создаем строку для IN условия
        placeholders = ','.join(['?'] * len(goodsids))

        # SQL запрос для получения цельных рулонов фибергласса
        sql = f"""
        SELECT
            g.marking as g_marking,
            g.goodsid,
            gg.width,
            gg.height,
            wh.qty - wh.reserveqty as available_qty,
            m.amfactor
        FROM goods g
        JOIN groupgoods gg ON gg.grgoodsid = g.grgoodsid
        JOIN grgoodsmeasure ggm ON ggm.grgoodsid = gg.grgoodsid
        JOIN measure m ON m.measureid = ggm.measureid
        JOIN groupgoodstypes ggt ON ggt.ggtypeid = gg.ggtypeid
        LEFT JOIN warehouse wh ON wh.goodsid = g.goodsid
        WHERE g.goodsid IN ({placeholders})
        AND ggm.ismain = 1
        AND gg.ggtypeid = 58
        AND gg.width > 0
        AND gg.height > 0
        AND (wh.qty - wh.reserveqty) > 0
        ORDER BY g.marking
        """

        if ENABLE_LOGGING:
            print(f"🔍 DB: Выполняем запрос материалов для goodsids={goodsids}")
            print(f"🔍 DB: SQL: {sql}")
            print(f"🔍 DB: Параметры: {goodsids}")

        cur.execute(sql, goodsids)
        rows = cur.fetchall()

        if ENABLE_LOGGING:
            print(f"🔍 DB: Запрос материалов вернул {len(rows)} строк")
            for i, row in enumerate(rows):
                print(f"   Строка {i+1}: goodsid={row[1]}, marking={row[0]}, width={row[2]}, height={row[3]}, qty={row[4]}")

        for row in rows:
            # Расчет количества рулонов
            available_qty = int(row[4]) if row[4] else 0
            width = float(row[2]) if row[2] else 0.0
            height = float(row[3]) if row[3] else 0.0
            amfactor = float(row[5]) if row[5] else 1.0

            # Количество целых рулонов: общее количество / (ширина * высота одного рулона)
            if width > 0 and height > 0:
                roll_area = width * height  # площадь одного рулона
                roll_count = int(available_qty / roll_area) if roll_area > 0 else 0

                if ENABLE_LOGGING:
                    print(f"   Расчет рулонов: {available_qty} / ({width} * {height}) = {available_qty} / {roll_area} = {roll_count} рулонов")
            else:
                roll_count = 0
                if ENABLE_LOGGING:
                    print(f"   Пропуск: нулевые размеры width={width}, height={height}")

            if roll_count > 0:
                material = FiberglassSheet(
                    goodsid=int(row[1]) if row[1] else 0,
                    marking=str(row[0]) if row[0] else "",
                    width=width,
                    height=height,
                    is_remainder=False,
                    remainder_id=None,
                    quantity=roll_count,
                    area_mm2=width * height
                )
                materials.append(material)

                if ENABLE_LOGGING:
                    print(f"🔍 DB: Загружен цельный рулон: {material.marking}, {material.width}x{material.height}мм, кол-во {material.quantity} рулонов")
            else:
                if ENABLE_LOGGING:
                    roll_area = width * height if width > 0 and height > 0 else 0
                    print(f"   Пропуск материала: {row[0]}, roll_count = {roll_count} (available_qty={available_qty}, roll_area={roll_area})")

        con.close()

    except Exception as e:
        if ENABLE_LOGGING:
            print(f"❌ Ошибка получения материалов фибергласса: {e}")
        raise

    if ENABLE_LOGGING:
        print(f"✅ Получено {len(materials)} цельных рулонов фибергласса")

    return materials

def get_fiberglass_warehouse_remainders(goodsids: List[int]) -> List[FiberglassSheet]:
    """
    Получить деловые остатки фибергласса со склада
    Адаптировано на основе запросов профилей для плоскостного материала
    """
    remainders = []

    if not goodsids:
        if ENABLE_LOGGING:
            print("⚠️ DB: goodsids пустой, пропускаем запрос остатков")
        return remainders

    try:
        con = get_db_connection()
        cur = con.cursor()

        # Создаем строку для IN условия
        placeholders = ','.join(['?'] * len(goodsids))

        # SQL запрос для получения деловых остатков фибергласса
        sql = f"""
        SELECT
            g.marking as g_marking,
            whm.goodsid,
            whm.width,
            whm.height,
            whm.qty - whm.reserveqty as qty,
            whm.whremainderid,
            (whm.width * whm.height) as area_mm2
        FROM warehouseremainder whm
        JOIN goods g ON g.goodsid = whm.goodsid
        JOIN groupgoods gg ON gg.grgoodsid = g.grgoodsid
        JOIN groupgoodstypes ggt ON ggt.ggtypeid = gg.ggtypeid
        WHERE whm.goodsid IN ({placeholders})
        AND gg.ggtypeid = 58
        AND (whm.qty - whm.reserveqty) > 0
        ORDER BY area_mm2 DESC
        """

        if ENABLE_LOGGING:
            print(f"🔍 DB: Выполняем запрос остатков для goodsids={goodsids}")
            print(f"🔍 DB: SQL: {sql}")
            print(f"🔍 DB: Параметры: {goodsids}")

        cur.execute(sql, goodsids)
        rows = cur.fetchall()

        if ENABLE_LOGGING:
            print(f"🔍 DB: Запрос остатков вернул {len(rows)} строк")
            for i, row in enumerate(rows):
                print(f"   Строка {i+1}: goodsid={row[1]}, marking={row[0]}, width={row[2]}, height={row[3]}, qty={row[4]}")

        for row in rows:
            remainder = FiberglassSheet(
                goodsid=int(row[1]) if row[1] else 0,
                marking=str(row[0]) if row[0] else "",
                width=float(row[2]) if row[2] else 0.0,
                height=float(row[3]) if row[3] else 0.0,
                is_remainder=True,
                remainder_id=int(row[5]) if row[5] else None,
                quantity=int(row[4]) if row[4] else 1,
                area_mm2=float(row[6]) if row[6] else 0.0
            )
            remainders.append(remainder)

            if ENABLE_LOGGING:
                print(f"🔍 DB: Загружен деловой остаток: {remainder.marking}, {remainder.width}x{remainder.height}мм, площадь {remainder.area_mm2:.0f}мм²")

        con.close()

    except Exception as e:
        if ENABLE_LOGGING:
            print(f"❌ Ошибка получения остатков фибергласса: {e}")
        raise

    if ENABLE_LOGGING:
        print(f"✅ Получено {len(remainders)} деловых остатков фибергласса")

    return remainders

def load_fiberglass_data(grorder_mos_id: int) -> FiberglassLoadDataResponse:
    """
    Загрузить все данные фибергласса по grorder_mos_id
    Объединяет детали, материалы и остатки в один метод
    """
    try:
        if ENABLE_LOGGING:
            print(f"🔄 Загрузка данных фибергласса для grorder_mos_id={grorder_mos_id}")

        # 1. Загружаем детали фибергласса
        details = get_fiberglass_details_by_grorder_mos_id(grorder_mos_id)

        if not details:
            if ENABLE_LOGGING:
                print(f"⚠️ Не найдено деталей фибергласса для grorder_mos_id={grorder_mos_id}")
            return FiberglassLoadDataResponse(
                details=[],
                materials=[],
                remainders=[],
                total_details=0,
                total_materials=0,
                total_remainders=0
            )

        # 2. Получаем уникальные goodsid для загрузки материалов
        goodsids = list(set(detail.goodsid for detail in details if detail.goodsid))

        if ENABLE_LOGGING:
            print(f"🔧 Найдено {len(goodsids)} уникальных артикулов для загрузки материалов: {goodsids}")

        # 3. Загружаем материалы и остатки
        materials = get_fiberglass_warehouse_materials(goodsids)
        remainders = get_fiberglass_warehouse_remainders(goodsids)

        response = FiberglassLoadDataResponse(
            details=details,
            materials=materials,
            remainders=remainders,
            total_details=len(details),
            total_materials=len(materials),
            total_remainders=len(remainders)
        )

        if ENABLE_LOGGING:
            print(f"✅ Данные фибергласса загружены:")
            print(f"   - Деталей: {response.total_details}")
            print(f"   - Цельных рулонов: {response.total_materials}")
            print(f"   - Деловых остатков: {response.total_remainders}")

        return response

    except Exception as e:
        if ENABLE_LOGGING:
            print(f"❌ Ошибка загрузки данных фибергласса: {e}")
        raise

