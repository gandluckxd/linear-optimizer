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
    delete_grorders_mos
    ,delete_optimized_mos_by_grorders_mos_id
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
        return created
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/optdetail-mos", response_model=OptDetailMos)
async def create_optdetail_mos(request: OptDetailMosCreate):
    """
    Создать запись в таблице OPTDETAIL_MOS
    """
    try:
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

        created = insert_optdetail_mos(
            optimized_mos_id=request.optimized_mos_id,
            orderid=request.orderid,
            qty=request.qty,
            itemsdetailid=enriched.get("itemsdetailid"),
            itemlong=request.itemlong,
            ug1=enriched.get("ug1"),
            ug2=enriched.get("ug2"),
            num=request.num,
            subnum=request.subnum,
            long_al=request.long_al,
            # Поменяли местами загрузку: izdpart <- partside, partside <- izdpart
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
        return created
    except Exception as e:
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