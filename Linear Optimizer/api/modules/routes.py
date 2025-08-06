"""
API эндпоинты для Linear Optimizer
"""

from fastapi import APIRouter, HTTPException
from typing import List
from modules.models import (
    ProfileRequest, StockRequest, Profile, Stock, 
    OptimizationResult, UploadRequest, MoskitkaRequest, MoskitkaProfile,
    StockRemainderRequest, StockMaterialRequest, StockRemainder, StockMaterial
)
from utils.db_functions import (
    get_profiles_for_order,
    get_stock_for_profile,
    save_optimization_result,
    get_moskitka_profiles,
    get_stock_remainders,
    get_stock_materials
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
        
        # Настройки оптимизации (можно получать из запроса)
        settings = OptimizationSettings(
            blade_width=request.get('blade_width', 5.0),
            min_remainder_length=request.get('min_remainder_length', 300.0),
            time_limit_seconds=request.get('time_limit', 300),
            solver_type=SolverType.CP_SAT  # Используем лучший алгоритм
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