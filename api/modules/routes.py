"""
API эндпоинты для Linear Optimizer
"""

from fastapi import APIRouter, HTTPException
from typing import List
from modules.models import (
    ProfileRequest, StockRequest, Profile, Stock, 
    OptimizationResult, UploadRequest, MoskitkaRequest, MoskitkaProfile,
    StockRemainderRequest, StockMaterialRequest, StockRemainder, StockMaterial,
    GrordersMosCreate, GrordersMos,
    OptimizedMosCreate, OptimizedMos,
    OptDetailMosCreate, OptDetailMos,
    GrordersByMosIdRequest
)
from modules.models import (
    FiberglassDetailRequest, FiberglassMaterialsRequest,
    FiberglassDetail, FiberglassSheet, FiberglassLoadDataResponse
)
from utils.db_functions import (
    get_profiles_for_order,
    get_stock_for_profile,
    save_optimization_result,
    get_moskitka_profiles,
    get_stock_remainders,
    get_stock_materials,
    insert_grorders_mos,
    insert_optimized_mos,
    insert_optdetail_mos,
    enrich_optdetail_mos_fields,
    get_grorder_ids_by_grorders_mos_id,
    delete_grorders_mos,
    delete_optimized_mos_by_grorders_mos_id,
    distribute_cell_numbers
)
from utils.db_functions import (
    load_fiberglass_data,
    get_fiberglass_details_by_grorder_mos_id,
    get_fiberglass_warehouse_materials,
    get_fiberglass_warehouse_remainders
)

router = APIRouter()

@router.post("/profiles", response_model=List[Profile])
async def get_profiles(request: ProfileRequest):
    """
    Получить список профилей для распила из заказа
    """
    try:
        profiles = get_profiles_for_order(request.order_id)
        return profiles
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stock", response_model=List[Stock])
async def get_stock(request: StockRequest):
    """
    Получить остатки профиля на складе
    """
    try:
        stock = get_stock_for_profile(request.profile_id)
        return stock
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/upload-result")
async def upload_result(request: UploadRequest):
    """
    Загрузить результаты оптимизации в Altawin
    """
    try:
        result = save_optimization_result(
            request.optimization_result,
            request.save_to_order,
            request.create_cutting_list
        )
        return {"status": "success", "message": "Результаты успешно загружены"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/optimized-mos/by-grorders-mos-id/{grorders_mos_id}")
async def delete_optimized_mos_by_grorders_mos_id_endpoint(grorders_mos_id: int):
    """
    Удалить все записи из OPTIMIZED_MOS и OPTDETAIL_MOS, связанные с GRORDER_MOS_ID
    """
    try:
        success = delete_optimized_mos_by_grorders_mos_id(grorders_mos_id)
        if not success:
            raise HTTPException(status_code=404, detail="Записи не найдены")
        return {"status": "success", "message": "Записи успешно удалены"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stock-remainders", response_model=List[StockRemainder])
async def get_stock_remainders_endpoint(request: StockRemainderRequest):
    """
    Получить остатки со склада по артикулам профилей
    """
    try:
        remainders = get_stock_remainders(request.profile_codes)
        return remainders
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stock-materials", response_model=List[StockMaterial])
async def get_stock_materials_endpoint(request: StockMaterialRequest):
    """
    Получить цельные материалы со склада по артикулам профилей
    """
    try:
        materials = get_stock_materials(request.profile_codes)
        return materials
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/diagnose-stock-materials")
async def diagnose_stock_materials_endpoint(request: StockMaterialRequest):
    """
    Диагностика проблем с загрузкой материалов со склада
    """
    try:
        from utils.db_functions import diagnose_stock_materials_issue
        diagnosis = diagnose_stock_materials_issue(request.profile_codes)
        return diagnosis
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/moskitka-profiles", response_model=List[MoskitkaProfile])
async def get_moskitka_profiles_endpoint(request: MoskitkaRequest):
    """
    Получить информацию о профилях москитных сеток для раскроя
    Принимает список ID групп заказов и возвращает все профили для оптимизации
    """
    try:
        profiles = get_moskitka_profiles(request.grorder_ids)
        return profiles
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/grorders-by-mos-id", response_model=List[int])
async def get_grorders_by_mos_id_endpoint(request: GrordersByMosIdRequest):
    """
    Получить список grorderid по идентификатору сменного задания москитных сеток (grorders_mos_id)
    """
    try:
        ids = get_grorder_ids_by_grorders_mos_id(request.grorders_mos_id)
        return ids
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/optimize")
async def optimize_profiles(request: dict):
    """
    Запустить оптимизацию распила профилей
    """
    try:
        # Импортируем оптимизатор локально (избегаем проблем с путями)
        import sys
        import os
        
        # Добавляем путь к клиентской части только если нужно
        client_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'client')
        if client_path not in sys.path:
            sys.path.insert(0, client_path)
        
        # Пытаемся импортировать с обработкой ошибок
        try:
            from core.optimizer import CuttingStockOptimizer, OptimizationSettings, SolverType
            from core.models import Profile as OptimizerProfile, Stock as OptimizerStock
        except ImportError as e:
            raise HTTPException(status_code=500, detail=f"Ошибка импорта оптимизатора: {str(e)}")
        
        # Получаем входные данные
        order_id = request.get('order_id')
        if not order_id:
            raise HTTPException(status_code=400, detail="order_id обязателен")
        
        # Настройки оптимизации: берем из запроса, без лишних полей
        settings = OptimizationSettings(
            blade_width=request.get('blade_width', 5.0),
            min_remainder_length=request.get('min_remainder_length', 300.0),
            max_waste_percent=request.get('max_waste_percent', 15.0),
            pair_optimization=bool(request.get('pair_optimization', True)),
            use_remainders=bool(request.get('use_remainders', True)),
            time_limit_seconds=request.get('time_limit_seconds', request.get('time_limit', 300)),
            begin_indent=request.get('begin_indent', 10.0),
            end_indent=request.get('end_indent', 10.0),
            min_trash_mm=request.get('min_trash_mm', 50.0),
        )
        
        # Получаем профили для распила
        profiles_data = get_profiles_for_order(order_id)
        if not profiles_data:
            return {"success": False, "message": "Нет профилей для распила"}
        
        # Получаем остатки для каждого уникального типа профиля
        profile_ids = list(set(p.id for p in profiles_data))
        all_stocks = []
        
        for profile_id in profile_ids:
            stocks = get_stock_for_profile(profile_id)
            all_stocks.extend(stocks)
        
        if not all_stocks:
            return {"success": False, "message": "Нет материалов на складе"}
        
        # Конвертируем в модели оптимизатора
        optimizer_profiles = [
            OptimizerProfile(
                id=p.id,
                order_id=p.order_id,
                element_name=p.element_name,
                profile_code=p.profile_code,
                length=p.length,
                quantity=p.quantity
            ) for p in profiles_data
        ]
        
        optimizer_stocks = [
            OptimizerStock(
                id=s.id,
                profile_id=s.profile_id,
                length=s.length,
                quantity=s.quantity,
                location=s.location or "",
                is_remainder=s.is_remainder
            ) for s in all_stocks
        ]
        
        # Запускаем оптимизацию
        optimizer = CuttingStockOptimizer(settings)
        result = optimizer.optimize(optimizer_profiles, optimizer_stocks)
        
        if result.success:
            return {
                "success": True,
                "message": result.message,
                "cut_plans": [
                    {
                        "stock_id": plan.stock_id,
                        "stock_length": plan.stock_length,
                        "cuts": plan.cuts,
                        "waste": plan.waste,
                        "waste_percent": plan.waste_percent,
                        "remainder": plan.remainder
                    } for plan in result.cut_plans
                ],
                "total_waste": result.total_waste,
                "total_waste_percent": result.total_waste_percent,
                "statistics": result.get_statistics()
            }
        else:
            return {
                "success": False,
                "message": result.message,
                "cut_plans": [],
                "total_waste": 0,
                "total_waste_percent": 0
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка оптимизации: {str(e)}")

@router.post("/grorders-mos", response_model=GrordersMos)
async def create_grorders_mos(request: GrordersMosCreate):
    """
    Создать запись в таблице GRORDERS_MOS
    """
    try:
        created = insert_grorders_mos(name=request.name)
        return created
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/optimized-mos", response_model=OptimizedMos)
async def create_optimized_mos(request: OptimizedMosCreate):
    """
    Создать запись в таблице OPTIMIZED_MOS
    """
    try:
        print(f"🔧 API: Создание записи в OPTIMIZED_MOS: grorder_mos_id={request.grorder_mos_id}, goodsid={request.goodsid}")
        
        created = insert_optimized_mos(
            grorder_mos_id=request.grorder_mos_id,
            goodsid=request.goodsid,
            qty=request.qty,
            isbar=request.isbar,
            longprof=request.longprof,
            cutwidth=request.cutwidth,
            border=request.border,
            minrest=request.minrest,
            mintrash=request.mintrash,
            map=request.map,
            ostat=request.ostat,
            sumprof=request.sumprof,
            restpercent=request.restpercent,
            trashpercent=request.trashpercent,
            beginindent=request.beginindent,
            endindent=request.endindent,
            sumtrash=request.sumtrash,
        )
        
        print(f"✅ API: Запись в OPTIMIZED_MOS создана успешно: id={created.id}")
        return created
        
    except Exception as e:
        print(f"❌ API: Ошибка создания записи в OPTIMIZED_MOS: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/optdetail-mos", response_model=OptDetailMos)
async def create_optdetail_mos(request: OptDetailMosCreate):
    """
    Создать запись в таблице OPTDETAIL_MOS
    """
    try:
        print(f"🔧 API: *** ОТЛАДКА *** Создание записи в OPTDETAIL_MOS: optimized_mos_id={request.optimized_mos_id}, orderid={request.orderid}")
        print(f"🔧 API: *** ОТЛАДКА *** Полный request: {request}")
        
        # Обогащаем поля перед вставкой, чтобы в insert_optdetail_mos попадали корректные значения
        enriched = enrich_optdetail_mos_fields(
            optimized_mos_id=request.optimized_mos_id,
            orderid=request.orderid,
            itemlong=request.itemlong,
            itemsdetailid=request.itemsdetailid,
            ug1=request.ug1,
            ug2=request.ug2,
            izdpart=request.izdpart,
            partside=request.partside,
            modelno=request.modelno,
            modelheight=request.modelheight,
            modelwidth=request.modelwidth,
            flugelopentype=request.flugelopentype,
            flugelcount=request.flugelcount,
            ishandle=request.ishandle,
            handlepos=request.handlepos,
            handleposfalts=request.handleposfalts,
            flugelopentag=request.flugelopentag,
        )

        # *** ИСПРАВЛЕНО *** Используем корректный orderid из функции обогащения
        final_orderid = enriched.get("orderid", request.orderid)
        
        print(f"🔧 API: *** ИСПРАВЛЕНО *** Используем orderid={final_orderid} (исходный={request.orderid})")
        
        created = insert_optdetail_mos(
            optimized_mos_id=request.optimized_mos_id,
            orderid=final_orderid,  # *** ИСПРАВЛЕНО *** Используем корректный orderid
            qty=request.qty,
            itemsdetailid=enriched.get("itemsdetailid"),
            itemlong=request.itemlong,
            ug1=enriched.get("ug1"),
            ug2=enriched.get("ug2"),
            num=request.num,
            subnum=request.subnum,
            long_al=request.long_al,
            # Исправлено: поля загружаются корректно
            izdpart=enriched.get("izdpart"),
            partside=enriched.get("partside"),
            modelno=enriched.get("modelno"),
            modelheight=enriched.get("modelheight"),
            modelwidth=enriched.get("modelwidth"),
            flugelopentype=enriched.get("flugelopentype"),
            flugelcount=enriched.get("flugelcount"),
            ishandle=enriched.get("ishandle"),
            handlepos=enriched.get("handlepos"),
            handleposfalts=enriched.get("handleposfalts"),
            flugelopentag=enriched.get("flugelopentag"),
        )
        
        print(f"✅ API: Запись в OPTDETAIL_MOS создана успешно: id={created.id}")
        return created
        
    except Exception as e:
        print(f"❌ API: Ошибка создания записи в OPTDETAIL_MOS: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/grorders-mos/{grorders_mos_id}")
async def delete_grorders_mos_endpoint(grorders_mos_id: int):
    """
    Удалить запись из таблицы GRORDERS_MOS по ID
    """
    try:
        success = delete_grorders_mos(grorders_mos_id)
        if not success:
            raise HTTPException(status_code=404, detail="Запись не найдена")
        return {"status": "success", "message": "Запись успешно удалена"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/adjust-materials-altawin")
async def adjust_materials_altawin(request: dict):
    """
    Скорректировать списание и приход материалов в Altawin для оптимизации москитных сеток
    """
    try:
        from utils.db_functions import adjust_materials_for_moskitka_optimization
        
        print(f"🔧 API: adjust_materials_altawin вызван с request: {request}")
        
        grorders_mos_id = request.get('grorders_mos_id')
        if not grorders_mos_id:
            raise HTTPException(status_code=400, detail="grorders_mos_id обязателен")
        
        # Получаем данные об использованных материалах и деловых остатках
        used_materials = request.get('used_materials', [])  # Список использованных материалов
        business_remainders = request.get('business_remainders', [])  # Список деловых остатков
        
        print(f"🔧 API: Получены данные:")
        print(f"   grorders_mos_id: {grorders_mos_id}")
        print(f"   used_materials: {len(used_materials)} записей")
        print(f"   business_remainders: {len(business_remainders)} записей")
        
        if used_materials:
            print(f"🔧 API: Детализация used_materials:")
            for i, material in enumerate(used_materials):
                print(f"   [{i}] goodsid={material.get('goodsid')}, length={material.get('length')}, quantity={material.get('quantity')}, is_remainder={material.get('is_remainder')}")
        
        if business_remainders:
            print(f"🔧 API: Детализация business_remainders:")
            for i, remainder in enumerate(business_remainders):
                print(f"   [{i}] goodsid={remainder.get('goodsid')}, length={remainder.get('length')}, quantity={remainder.get('quantity')}")
        
        result = adjust_materials_for_moskitka_optimization(
            grorders_mos_id, 
            used_materials, 
            business_remainders
        )
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка корректировки материалов: {str(e)}")

@router.post("/distribute-cell-numbers")
async def distribute_cell_numbers_endpoint(request: dict):
    """
    Распределить номера ячеек для оптимизации москитных сеток.
    Выполняется ПОСЛЕ загрузки данных оптимизации в altawin.
    """
    try:
        grorder_mos_id = request.get('grorder_mos_id')
        if not grorder_mos_id:
            raise HTTPException(status_code=400, detail="grorder_mos_id обязателен")
        
        print(f"🔧 API: distribute_cell_numbers вызван для grorder_mos_id={grorder_mos_id}")
        
        result = distribute_cell_numbers(grorder_mos_id)
        
        if result["success"]:
            print(f"✅ API: Распределение ячеек выполнено успешно: обработано {result['processed_items']} проемов")
        else:
            print(f"❌ API: Ошибка распределения ячеек: {result.get('error', result.get('message'))}")
        
        return result
        
    except Exception as e:
        print(f"❌ API: Ошибка распределения ячеек: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка распределения ячеек: {str(e)}")

@router.get("/test-connection")
async def test_connection():
    """
    Проверить соединение с базой данных
    """
    try:
        from utils.db_functions import test_db_connection
        is_connected = test_db_connection()
        return {
            "status": "connected" if is_connected else "disconnected", 
            "database": "Altawin"
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


# ========================================
# ЭНДПОИНТЫ ДЛЯ ФИБЕРГЛАССА
# ========================================

@router.post("/fiberglass/load-data", response_model=FiberglassLoadDataResponse)
async def load_fiberglass_data_endpoint(request: FiberglassDetailRequest):
    """
    Загрузить все данные фибергласса по grorder_mos_id
    (детали, материалы, остатки)
    """
    try:
        print(f"🔄 API: Загрузка данных фибергласса для grorder_mos_id={request.grorder_mos_id}")
        
        data = load_fiberglass_data(request.grorder_mos_id)
        
        print(f"✅ API: Данные фибергласса загружены:")
        print(f"   - Деталей: {data.total_details}")
        print(f"   - Цельных рулонов: {data.total_materials}")
        print(f"   - Деловых остатков: {data.total_remainders}")
        
        return data
        
    except Exception as e:
        print(f"❌ API: Ошибка загрузки данных фибергласса: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки данных фибергласса: {str(e)}")

@router.post("/fiberglass/get-details", response_model=List[FiberglassDetail])
async def get_fiberglass_details_endpoint(request: FiberglassDetailRequest):
    """
    Получить детали фибергласса для раскроя по grorder_mos_id
    """
    try:
        details = get_fiberglass_details_by_grorder_mos_id(request.grorder_mos_id)
        print(f"🔍 API: Возвращаем {len(details)} деталей фибергласса")
        for i, detail in enumerate(details[:3]):  # Логируем первые 3 детали
            print(f"🔍 API: Деталь {i+1}: {detail.marking}, izdpart='{detail.izdpart}', partside='{detail.partside}'")
        return details
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения деталей фибергласса: {str(e)}")

@router.post("/fiberglass/get-materials", response_model=List[FiberglassSheet])
async def get_fiberglass_materials_endpoint(request: FiberglassMaterialsRequest):
    """
    Получить материалы фибергласса со склада
    """
    try:
        materials = get_fiberglass_warehouse_materials(request.goodsids)
        return materials
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения материалов фибергласса: {str(e)}")

@router.post("/fiberglass/get-remainders", response_model=List[FiberglassSheet])
async def get_fiberglass_remainders_endpoint(request: FiberglassMaterialsRequest):
    """
    Получить деловые остатки фибергласса
    """
    try:
        remainders = get_fiberglass_warehouse_remainders(request.goodsids)
        return remainders
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения остатков фибергласса: {str(e)}")

