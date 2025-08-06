"""
API клиент для взаимодействия с Linear Optimizer API
"""

import requests
from typing import List, Dict, Optional
from core.models import Profile, Stock, OptimizationResult, CutPlan, StockRemainder, StockMaterial
import json
from datetime import datetime

class APIClient:
    """Клиент для работы с API"""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.session = requests.Session()
        
    def test_connection(self) -> bool:
        """Проверить соединение с API"""
        try:
            response = self.session.get(f"{self.base_url}/api/test-connection", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def get_profiles(self, order_id: int) -> List[Profile]:
        """Получить список профилей для заказа"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/profiles",
                json={"order_id": order_id},
                timeout=30
            )
            response.raise_for_status()
            
            profiles = []
            for data in response.json():
                profile = Profile(
                    id=data['id'],
                    order_id=data['order_id'],
                    element_name=data['element_name'],
                    profile_code=data['profile_code'],
                    length=data['length'],
                    quantity=data['quantity']
                )
                profiles.append(profile)
            
            return profiles
            
        except requests.RequestException as e:
            raise Exception(f"Ошибка получения профилей: {str(e)}")
    
    def get_stock(self, profile_id: int) -> List[Stock]:
        """Получить остатки профиля на складе"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/stock",
                json={"profile_id": profile_id},
                timeout=30
            )
            response.raise_for_status()
            
            stocks = []
            for data in response.json():
                stock = Stock(
                    id=data['id'],
                    profile_id=data['profile_id'],
                    length=data['length'],
                    quantity=data['quantity'],
                    location=data.get('location', ''),
                    is_remainder=data.get('is_remainder', False)
                )
                stocks.append(stock)
            
            return stocks
            
        except requests.RequestException as e:
            raise Exception(f"Ошибка получения остатков: {str(e)}")
    
    def get_stock_remainders(self, profile_codes: List[str]) -> List[StockRemainder]:
        """Получить остатки со склада по артикулам профилей"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/stock-remainders",
                json={"profile_codes": profile_codes},
                timeout=30
            )
            response.raise_for_status()
            
            remainders = []
            for data in response.json():
                remainder = StockRemainder(
                    profile_code=data['profile_code'],
                    length=data['length'],
                    quantity_pieces=data['quantity_pieces']
                )
                remainders.append(remainder)
            
            return remainders
            
        except requests.RequestException as e:
            raise Exception(f"Ошибка получения остатков: {str(e)}")
    
    def get_stock_materials(self, profile_codes: List[str]) -> List[StockMaterial]:
        """Получить цельные материалы со склада по артикулам профилей"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/stock-materials",
                json={"profile_codes": profile_codes},
                timeout=30
            )
            response.raise_for_status()
            
            materials = []
            for data in response.json():
                material = StockMaterial(
                    profile_code=data['profile_code'],
                    length=data['length'],
                    quantity_pieces=data['quantity_pieces']
                )
                materials.append(material)
            
            return materials
            
        except requests.RequestException as e:
            raise Exception(f"Ошибка получения материалов: {str(e)}")
    
    def upload_optimization_result(self, order_id: int, result: OptimizationResult,
                                 save_to_order: bool = True,
                                 create_cutting_list: bool = True) -> bool:
        """Загрузить результаты оптимизации в Altawin"""
        try:
            # Преобразуем результат в формат для API
            data = {
                "optimization_result": {
                    "order_id": order_id,
                    "cut_plans": [
                        {
                            "stock_id": plan.stock_id,
                            "stock_length": plan.stock_length,
                            "cuts": plan.cuts,
                            "waste": plan.waste,
                            "waste_percent": plan.waste_percent,
                            "remainder": plan.remainder
                        }
                        for plan in result.cut_plans
                    ],
                    "total_waste": result.total_waste,
                    "total_waste_percent": result.total_waste_percent,
                    "profiles_cut": sum(sum(cut['quantity'] for cut in plan.cuts) 
                                      for plan in result.cut_plans),
                    "stocks_used": len(result.cut_plans),
                    "created_at": result.created_at.isoformat()
                },
                "save_to_order": save_to_order,
                "create_cutting_list": create_cutting_list
            }
            
            response = self.session.post(
                f"{self.base_url}/api/upload-result",
                json=data,
                timeout=60
            )
            response.raise_for_status()
            
            return True
            
        except requests.RequestException as e:
            raise Exception(f"Ошибка загрузки результатов: {str(e)}")

# Глобальный экземпляр клиента
_api_client = None

def get_api_client() -> APIClient:
    """Получить глобальный экземпляр API клиента"""
    global _api_client
    if _api_client is None:
        _api_client = APIClient()
    return _api_client

def set_api_url(url: str):
    """Установить URL API"""
    global _api_client
    _api_client = APIClient(url) 