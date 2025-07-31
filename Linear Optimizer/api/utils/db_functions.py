"""
Функции для работы с базой данных Altawin
"""

import fdb
from modules.config import DB_CONFIG, ENABLE_LOGGING
from modules.models import Profile, Stock, MoskitkaProfile, StockRemainder, StockMaterial
from typing import List

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
            
            # Формируем карту распила (MAP) - простое текстовое представление
            cut_map = "; ".join([
                f"{cut['quantity']}x{cut['length']}мм" 
                for cut in plan.cuts
            ])
            
            cur.execute(insert_optdata_sql, (
                optimization_result.order_id,  # SHIFTTASKSID (ID сменного задания)
                plan.stock_id,  # GOODSID (это может быть не правильно, нужно уточнить)
                1,  # QTY (количество хлыстов этого типа)
                plan.stock_length,  # LONGPROF (длина хлыста)
                3.0,  # CUTWIDTH (ширина пропила)
                100.0,  # MINREST (минимальный остаток)
                plan.remainder or plan.waste,  # OSTAT (остаток)
                plan.get_used_length(),  # SUMPROF (сумма отпиленных кусков)
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