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

    def get_grorders_by_mos_id(self, grorders_mos_id: int) -> List[int]:
        """Получить список grorderid по идентификатору сменного задания москитных сеток"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/grorders-by-mos-id",
                json={"grorders_mos_id": grorders_mos_id},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list):
                raise Exception("Неверный формат ответа при получении grorderid")
            return [int(x) for x in data]
        except requests.RequestException as e:
            raise Exception(f"Ошибка получения grorderid по mos_id: {str(e)}")
    
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

    # ===== Методы для загрузки данных в OPTIMIZED_MOS и OPTDETAIL_MOS =====

    def delete_optimized_mos_by_grorders_mos_id(self, grorders_mos_id: int) -> bool:
        """Удалить все записи OPTIMIZED_MOS/OPTDETAIL_MOS по GRORDER_MOS_ID"""
        try:
            response = self.session.delete(
                f"{self.base_url}/api/optimized-mos/by-grorders-mos-id/{grorders_mos_id}",
                timeout=30,
            )
            # 200 - удалено; 404 - записей не было (это не ошибка для нас)
            if response.status_code in (200, 204, 404):
                return True
            # Иные коды считаем ошибкой
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            raise Exception(f"Ошибка удаления данных MOS: {str(e)}")

    def create_optimized_mos(self, payload: Dict) -> Dict:
        """Создать запись в OPTIMIZED_MOS"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/optimized-mos",
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise Exception(f"Ошибка создания OPTIMIZED_MOS: {str(e)}")

    def create_optdetail_mos(self, payload: Dict) -> Dict:
        """Создать запись в OPTDETAIL_MOS"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/optdetail-mos",
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise Exception(f"Ошибка создания OPTDETAIL_MOS: {str(e)}")

    def upload_mos_data(
        self,
        grorders_mos_id: int,
        result: OptimizationResult,
        profiles: List[Profile],
        blade_width_mm: int = 5,
        min_remainder_mm: int = 300,
        begin_indent_mm: int = 0,
        end_indent_mm: int = 0,
        min_trash_mm: int = 50,
    ) -> bool:
        """
        Загрузить данные оптимизации в таблицы OPTIMIZED_MOS и OPTDETAIL_MOS.

        Args:
            grorders_mos_id: Идентификатор сменного задания москитных сеток
            result: Результат оптимизации
            profiles: Оригинальные профили (для маппинга goodsid->orderid)
            blade_width_mm: Ширина пропила (CUTWIDTH)
            min_remainder_mm: Минимальный остаток (MINREST)
            isbar: Признак ISBAR
        """
        try:
            if not result or not getattr(result, 'cut_plans', None):
                raise Exception("Нет данных оптимизации для выгрузки")

            # Маппинги для удобства
            goodsid_to_orderid: Dict[int, int] = {}
            for p in profiles:
                # В наших профилях id = goodsid, order_id = grorderid
                goodsid_to_orderid[int(p.id)] = int(p.order_id)

            # Очистка предыдущих данных для текущего сменного задания
            self.delete_optimized_mos_by_grorders_mos_id(grorders_mos_id)

            # Основная выгрузка
            for plan in result.cut_plans:
                cuts = plan.cuts or []
                if not cuts:
                    continue

                # Выбираем основной goodsid по большинству кусков в плане
                goodsid_counter: Dict[int, int] = {}
                for cut in cuts:
                    pid = int(cut.get('profile_id', 0)) if isinstance(cut, dict) else 0
                    if pid:
                        goodsid_counter[pid] = goodsid_counter.get(pid, 0) + int(cut.get('quantity', 0) or 0)
                main_goodsid = 0
                if goodsid_counter:
                    main_goodsid = max(goodsid_counter.items(), key=lambda x: x[1])[0]

                # Формируем карту распила в формате OPTIMIZED.MAP:
                # последовательность длин (мм) с одним десятичным знаком,
                # каждая длина повторяется qty раз, разделитель ';'
                pieces_list = []
                for c in cuts:
                    length_val = float(c.get('length', 0) or 0)
                    qty_val = int(c.get('quantity', 0) or 0)
                    for _ in range(max(0, qty_val)):
                        pieces_list.append(f"{length_val:.1f}")
                cut_map = ";".join(pieces_list)

                sumprof = sum(float(c.get('length', 0)) * int(c.get('quantity', 0) or 0) for c in cuts)
                remainder = getattr(plan, 'remainder', None)
                waste = getattr(plan, 'waste', 0) or 0
                stock_length = float(getattr(plan, 'stock_length', 0) or 0)
                ostat = float(remainder) if remainder and remainder > 0 else float(waste)
                restpercent = (float(remainder) / stock_length * 100) if remainder and stock_length > 0 else 0.0
                trashpercent = float(getattr(plan, 'waste_percent', 0) or 0)

                # Создаем OPTIMIZED_MOS: по одной записи на каждый хлыст (count)
                # Определяем ISBAR корректно: 1 если исходный материал остаток, иначе 0
                isbar_value = 1 if bool(getattr(plan, 'is_remainder', False)) else 0
                # BORDER = beginindent + endindent
                border_value = int((begin_indent_mm or 0) + (end_indent_mm or 0))
                plan_count = int(getattr(plan, 'count', 1) or 1)

                for bar_index in range(1, plan_count + 1):
                    optimized_payload = {
                        "grorder_mos_id": int(grorders_mos_id),
                        "goodsid": int(main_goodsid or 0),
                        "qty": 1,  # одна запись на один хлыст
                        "isbar": isbar_value,
                        "longprof": stock_length,
                        "cutwidth": int(blade_width_mm),
                        "border": border_value,
                        "minrest": int(min_remainder_mm),
                        "mintrash": int(min_trash_mm),
                        "map": cut_map,
                        "ostat": float(ostat),
                        "sumprof": float(sumprof),
                        "restpercent": float(restpercent),
                        "trashpercent": float(trashpercent),
                        "beginindent": int(begin_indent_mm or 0),
                        "endindent": int(end_indent_mm or 0),
                        "sumtrash": float(waste) if waste else None,
                    }

                    optimized_resp = self.create_optimized_mos(optimized_payload)
                    optimized_mos_id = int(optimized_resp.get("id"))

                    # Детали распила для текущего хлыста
                    subnum_counter = 1
                    for c in cuts:
                        length_val = float(c.get('length', 0) or 0)
                        qty_val = int(c.get('quantity', 0) or 0)
                        pid = int(c.get('profile_id', 0) or 0)
                        order_id_for_piece = goodsid_to_orderid.get(pid) if pid in goodsid_to_orderid else None

                        if qty_val <= 0 or length_val <= 0:
                            continue

                        detail_payload = {
                            "optimized_mos_id": optimized_mos_id,
                            "orderid": int(order_id_for_piece or 0),
                            "qty": int(qty_val),
                            "itemsdetailid": None,
                            "itemlong": float(length_val),
                            "ug1": None,
                            "ug2": None,
                            "num": bar_index,  # номер хлыста в плане
                            "subnum": subnum_counter,
                            "long_al": float(length_val) + float(blade_width_mm),
                            "izdpart": None,
                            "partside": None,
                            "modelno": None,
                            "modelheight": None,
                            "modelwidth": None,
                            "flugelopentype": None,
                            "flugelcount": None,
                            "ishandle": None,
                            "handlepos": None,
                            "handleposfalts": None,
                            "flugelopentag": None,
                        }

                        self.create_optdetail_mos(detail_payload)
                        subnum_counter += 1

            return True

        except Exception as e:
            raise Exception(f"Ошибка загрузки данных MOS: {str(e)}")

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