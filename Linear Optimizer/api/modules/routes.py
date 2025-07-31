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
        # TODO: Реализовать после получения SQL запроса от Артема
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
        # TODO: Реализовать после получения SQL запроса от Артема
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
        # TODO: Реализовать после получения SQL запроса от Артема
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

@router.get("/test-connection")
async def test_connection():
    """
    Проверить соединение с базой данных
    """
    try:
        # TODO: Реализовать проверку соединения
        return {"status": "connected", "database": "Altawin"}
    except Exception as e:
        return {"status": "error", "detail": str(e)} 