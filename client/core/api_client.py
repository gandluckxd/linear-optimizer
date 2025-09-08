"""
API клиент для взаимодействия с Linear Optimizer API
"""

import requests
from typing import List, Dict
from core.models import Profile, Stock, OptimizationResult, StockRemainder, StockMaterial, FiberglassDetail, FiberglassSheet, FiberglassLoadDataResponse

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
                timeout=120
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
                    quantity=data['quantity'],
                    orderitemsid=data.get('orderitemsid'),
                    izdpart=data.get('izdpart'),
                    itemsdetailid=data.get('itemsdetailid')
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
                timeout=120
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
                    is_remainder=data.get('is_remainder', False),
                    warehouseremaindersid=data.get('warehouseremaindersid', None)
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
                timeout=120
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
                timeout=120
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

    def get_fiberglass_details(self, grorder_mos_id: int) -> List[FiberglassDetail]:
        """Получить детали полотен фибергласса для раскроя"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/fiberglass/get-details",
                json={"grorder_mos_id": grorder_mos_id},
                timeout=120
            )
            response.raise_for_status()

            details = []
            for data in response.json():
                detail = FiberglassDetail(
                    grorder_mos_id=data['grorder_mos_id'],
                    orderid=data['orderid'],
                    orderitemsid=data['orderitemsid'],
                    itemsdetailid=data['itemsdetailid'],
                    item_name=data['item_name'],
                    width=data['width'],
                    height=data['height'],
                    quantity=data['quantity'],
                    modelno=data.get('modelno'),
                    partside=data.get('partside'),
                    izdpart=data.get('izdpart'),
                    goodsid=data['goodsid'],
                    marking=data['marking'],
                    orderno=data.get('orderno', '')
                )
                details.append(detail)

                # Логирование для отладки
                print(f"🔍 API: Получена деталь из API: {detail.marking}")
                print(f"🔍 API:   partside='{detail.partside}', izdpart='{detail.izdpart}'")

            return details

        except requests.RequestException as e:
            raise Exception(f"Ошибка получения деталей полотен: {str(e)}")

    def get_fiberglass_remainders(self, goodsids: List[int]) -> List[FiberglassSheet]:
        """Получить остатки полотен со склада"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/fiberglass/get-remainders",
                json={"goodsids": goodsids},
                timeout=120
            )
            response.raise_for_status()

            remainders = []
            for data in response.json():
                remainder = FiberglassSheet(
                    goodsid=data['goodsid'],
                    marking=data['marking'],
                    width=data['width'],
                    height=data['height'],
                    is_remainder=data['is_remainder'],
                    remainder_id=data.get('remainder_id'),
                    quantity=data['quantity'],
                    area_mm2=data.get('area_mm2')
                )
                remainders.append(remainder)

            return remainders

        except requests.RequestException as e:
            raise Exception(f"Ошибка получения остатков полотен: {str(e)}")

    def get_fiberglass_materials(self, goodsids: List[int]) -> List[FiberglassSheet]:
        """Получить материалы полотен со склада"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/fiberglass/get-materials",
                json={"goodsids": goodsids},
                timeout=120
            )
            response.raise_for_status()

            materials = []
            data_list = response.json()
            print(f"📦 Клиент получил {len(data_list)} материалов полотен от сервера")

            for data in data_list:
                material = FiberglassSheet(
                    goodsid=data['goodsid'],
                    marking=data['marking'],
                    width=data['width'],
                    height=data['height'],
                    is_remainder=data['is_remainder'],
                    remainder_id=data.get('remainder_id'),
                    quantity=data['quantity'],
                    area_mm2=data.get('area_mm2')
                )
                materials.append(material)
                print(f"  - {material.marking}: {material.width}x{material.height}мм = {material.quantity} рулонов")

            return materials

        except requests.RequestException as e:
            raise Exception(f"Ошибка получения материалов полотен: {str(e)}")

    def load_fiberglass_data(self, grorder_mos_id: int) -> FiberglassLoadDataResponse:
        """Загрузить все данные фибергласса по grorder_mos_id"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/fiberglass/load-data",
                json={"grorder_mos_id": grorder_mos_id},
                timeout=120
            )
            response.raise_for_status()

            data = response.json()
            return FiberglassLoadDataResponse(
                details=data['details'],
                materials=data['materials'],
                remainders=data['remainders'],
                total_details=data['total_details'],
                total_materials=data['total_materials'],
                total_remainders=data['total_remainders']
            )

        except requests.RequestException as e:
            raise Exception(f"Ошибка загрузки данных фибергласса: {str(e)}")

    def get_grorders_by_mos_id(self, grorders_mos_id: int) -> List[int]:
        """Получить список grorderid по идентификатору сменного задания москитных сеток"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/grorders-by-mos-id",
                json={"grorders_mos_id": grorders_mos_id},
                timeout=120
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
                timeout=120
            )
            response.raise_for_status()
            
            return True
            
        except requests.RequestException as e:
            raise Exception(f"Ошибка загрузки результатов: {str(e)}")

    # ===== Методы для загрузки данных в OPTIMIZED_MOS и OPTDETAIL_MOS =====

    def delete_optimized_mos_by_grorders_mos_id(self, grorders_mos_id: int) -> bool:
        """Удалить все записи OPTIMIZED_MOS/OPTDETAIL_MOS по GRORDER_MOS_ID"""
        try:
            print(f"🔧 API Client: Удаление данных MOS для grorders_mos_id={grorders_mos_id}")
            
            response = self.session.delete(
                f"{self.base_url}/api/optimized-mos/by-grorders-mos-id/{grorders_mos_id}",
                timeout=120
            )
            
            if response.status_code == 200:
                print(f"✅ API Client: Данные MOS успешно удалены для grorders_mos_id={grorders_mos_id}")
                return True
            elif response.status_code == 404:
                print(f"⚠️ API Client: Данные MOS не найдены для grorders_mos_id={grorders_mos_id} (возможно, уже удалены)")
                return True  # Считаем успехом, если данных нет
            else:
                print(f"❌ API Client: Ошибка удаления данных MOS: HTTP {response.status_code}")
                response.raise_for_status()
                return True
                
        except requests.RequestException as e:
            print(f"❌ API Client: Ошибка удаления данных MOS: {str(e)}")
            raise Exception(f"Ошибка удаления данных MOS: {str(e)}")

    def create_optimized_mos(self, payload: Dict) -> Dict:
        """Создать запись в OPTIMIZED_MOS"""
        try:
            print(f"🔧 API Client: Отправка запроса создания OPTIMIZED_MOS: grorder_mos_id={payload.get('grorder_mos_id')}, goodsid={payload.get('goodsid')}")
            
            response = self.session.post(
                f"{self.base_url}/api/optimized-mos",
                json=payload,
                timeout=120
            )
            response.raise_for_status()
            
            result = response.json()
            print(f"✅ API Client: OPTIMIZED_MOS создан успешно: id={result.get('id')}")
            return result
            
        except requests.RequestException as e:
            print(f"❌ API Client: Ошибка создания OPTIMIZED_MOS: {str(e)}")
            raise Exception(f"Ошибка создания OPTIMIZED_MOS: {str(e)}")

    def create_optdetail_mos_bulk(self, payloads: List[Dict]) -> List[Dict]:
        """Массово создать записи в OPTDETAIL_MOS"""
        try:
            if not payloads:
                return []
            
            print(f"🔧 API Client: Отправка запроса на массовое создание {len(payloads)} записей OPTDETAIL_MOS")
            
            response = self.session.post(
                f"{self.base_url}/api/optdetail-mos/bulk",
                json=payloads,
                timeout=300  # Увеличенный таймаут для массовой операции
            )
            response.raise_for_status()
            
            result = response.json()
            print(f"✅ API Client: Массовое создание OPTDETAIL_MOS завершено, создано {len(result)} записей.")
            return result
            
        except requests.RequestException as e:
            print(f"❌ API Client: Ошибка массового создания OPTDETAIL_MOS: {str(e)}")
            raise Exception(f"Ошибка массового создания OPTDETAIL_MOS: {str(e)}")


    def create_optdetail_mos(self, payload: Dict) -> Dict:
        """Создать запись в OPTDETAIL_MOS"""
        try:
            print(f"🔧 API Client: Отправка запроса создания OPTDETAIL_MOS: optimized_mos_id={payload.get('optimized_mos_id')}, orderid={payload.get('orderid')}")
            
            response = self.session.post(
                f"{self.base_url}/api/optdetail-mos",
                json=payload,
                timeout=120
            )
            response.raise_for_status()
            
            result = response.json()
            print(f"✅ API Client: OPTDETAIL_MOS создан успешно: id={result.get('id')}")
            return result
            
        except requests.RequestException as e:
            print(f"❌ API Client: Ошибка создания OPTDETAIL_MOS: {str(e)}")
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
            print(f"🔧 API Client: *** ИСПРАВЛЕННАЯ ВЕРСИЯ *** Начало загрузки данных оптимизации для grorders_mos_id={grorders_mos_id}")
            print(f"🔧 API Client: Количество планов распила: {len(result.cut_plans) if result.cut_plans else 0}")
            print(f"🔧 API Client: *** ВЕРСИЯ С ИСПРАВЛЕНИЕМ ORDERID ***")
            
            if not result or not getattr(result, 'cut_plans', None):
                raise Exception("Нет данных оптимизации для выгрузки")

            # Теперь order_id будет содержаться прямо в cuts, поэтому маппинг не нужен
            # Оставляем только для отладочной информации
            profile_orderids = set(p.order_id for p in profiles)
            print(f"🔧 API Client: Профили содержат {len(profiles)} записей из {len(profile_orderids)} заказов")
            print(f"🔧 API Client: Список orderid в профилях: {sorted(profile_orderids)}")
            print(f"🔧 API Client: Теперь order_id будет браться прямо из результатов оптимизации")

            # Очистка предыдущих данных для текущего сменного задания
            print(f"🔧 API Client: Очистка предыдущих данных для grorders_mos_id={grorders_mos_id}")
            self.delete_optimized_mos_by_grorders_mos_id(grorders_mos_id)
            print(f"✅ API Client: Предыдущие данные очищены")

            # Основная выгрузка
            total_optimized_mos = 0
            optdetail_payloads = [] # Список для всех деталей
            
            for plan_index, plan in enumerate(result.cut_plans):
                print(f"🔧 API Client: Обработка плана {plan_index + 1}/{len(result.cut_plans)}")
                
                cuts = plan.cuts or []
                if not cuts:
                    print(f"⚠️ API Client: План {plan_index + 1} не содержит распилов, пропускаем")
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
                
                print(f"🔧 API Client: Основной goodsid для плана {plan_index + 1}: {main_goodsid}")

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

                print(f"🔧 API Client: Создание {plan_count} записей OPTIMIZED_MOS для плана {plan_index + 1}")

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

                    print(f"🔧 API Client: Создание OPTIMIZED_MOS {bar_index}/{plan_count} для плана {plan_index + 1}")
                    optimized_resp = self.create_optimized_mos(optimized_payload)
                    optimized_mos_id = int(optimized_resp.get("id"))
                    total_optimized_mos += 1
                    print(f"✅ API Client: OPTIMIZED_MOS создан с ID {optimized_mos_id}")

                    # Детали распила для текущего хлыста
                    subnum_counter = 1
                    
                    for c in cuts:
                        length_val = float(c.get('length', 0) or 0)
                        qty_val = int(c.get('quantity', 0) or 0)
                        pid = int(c.get('profile_id', 0) or 0)
                        
                        # Подробная отладка содержимого cut
                        print(f"🔍 API Client: Содержимое cut: {c}")
                        
                        # *** ИСПРАВЛЕНО *** order_id берется прямо из результатов оптимизации
                        # Это корректный ORDERID из таблицы ORDERS, который передается в OPTDETAIL_MOS
                        final_orderid = int(c.get('order_id', 0) or 0)

                        if qty_val <= 0 or length_val <= 0:
                            continue

                        # Отладочная информация
                        if final_orderid == 0:
                            print(f"⚠️ API Client: Для детали goodsid={pid} не найден order_id в результатах оптимизации!")
                        
                        print(f"🔧 API Client: Деталь {subnum_counter}: goodsid={pid}, orderid={final_orderid}, длина={length_val}, кол-во={qty_val}")

                        detail_payload = {
                            "optimized_mos_id": optimized_mos_id,
                            "orderid": final_orderid,
                            "qty": int(qty_val),
                            "itemsdetailid": c.get('itemsdetailid'),
                            "itemlong": float(length_val),
                            "ug1": None,
                            "ug2": None,
                            "num": bar_index,  # номер хлыста в плане
                            "subnum": subnum_counter,
                            "long_al": float(length_val) + float(blade_width_mm),
                            "izdpart": c.get('izdpart'),
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
                        optdetail_payloads.append(detail_payload)
                        subnum_counter += 1
            
            # Массовая вставка всех деталей одним запросом
            if optdetail_payloads:
                print(f"🔧 API Client: Запуск массовой вставки {len(optdetail_payloads)} записей OPTDETAIL_MOS.")
                self.create_optdetail_mos_bulk(optdetail_payloads)
            else:
                print("⚠️ API Client: Нет деталей для вставки в OPTDETAIL_MOS.")


            print(f"✅ API Client: Загрузка данных завершена успешно!")
            print(f"✅ API Client: Создано записей OPTIMIZED_MOS: {total_optimized_mos}")
            print(f"✅ API Client: Создано записей OPTDETAIL_MOS: {len(optdetail_payloads)}")
            
            return True

        except Exception as e:
            print(f"❌ API Client: Ошибка загрузки данных MOS: {str(e)}")
            raise Exception(f"Ошибка загрузки данных MOS: {str(e)}")

    def distribute_cell_numbers(self, grorders_mos_id: int, cell_map: Dict[str, int] = None) -> dict:
        """
        Распределить номера ячеек для оптимизации москитных сеток.
        Выполняется ПОСЛЕ загрузки данных оптимизации в altawin.
        
        Args:
            grorders_mos_id: ID сменного задания москитных сеток
            cell_map (Dict[str, int], optional): Карта для распределения ячеек.
                                                Ключ: f"{orderitemsid}_{izdpart}", Значение: cell_number.
                                                По умолчанию None.
            
        Returns:
            dict: Результат операции с информацией о количестве обработанных проемов
        """
        try:
            print(f"🔧 API Client: distribute_cell_numbers вызван для grorders_mos_id={grorders_mos_id}")
            
            payload = {
                "grorder_mos_id": grorders_mos_id
            }
            if cell_map:
                payload["cell_map"] = cell_map
                print(f"🔧 API Client: Отправка с картой ячеек ({len(cell_map)} записей).")
            
            response = self.session.post(f"{self.base_url}/api/distribute-cell-numbers", json=payload)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("success"):
                print(f"✅ API Client: Распределение ячеек выполнено успешно: обработано {result.get('processed_items', 0)} проемов")
            else:
                print(f"❌ API Client: Ошибка распределения ячеек: {result.get('error', result.get('message'))}")
            
            return result
            
        except Exception as e:
            print(f"❌ API Client: Ошибка распределения ячеек: {str(e)}")
            raise Exception(f"Ошибка распределения ячеек: {str(e)}")

    def adjust_materials_altawin(self, grorders_mos_id: int, used_materials: list = None, business_remainders: list = None, used_fiberglass_sheets: list = None, new_fiberglass_remainders: list = None) -> dict:
        """
        Скорректировать списание и приход материалов в Altawin для оптимизации москитных сеток
        
        Args:
            grorders_mos_id: ID сменного задания москитных сеток
            used_materials: Список использованных материалов [{'goodsid': int, 'length': float, 'quantity': int, 'is_remainder': bool}]
            business_remainders: Список деловых остатков [{'goodsid': int, 'length': float, 'quantity': int}]
            used_fiberglass_sheets: Список использованных листов/остатков фибергласса
            new_fiberglass_remainders: Список новых деловых остатков фибергласса
            
        Returns:
            dict: Результат операции
        """
        try:
            print(f"🔧 API Client: adjust_materials_altawin вызван с параметрами:")
            print(f"   grorders_mos_id: {grorders_mos_id}")
            print(f"   used_materials (профили): {len(used_materials) if used_materials else 0} записей")
            print(f"   business_remainders (профили): {len(business_remainders) if business_remainders else 0} записей")
            print(f"   used_fiberglass_sheets: {len(used_fiberglass_sheets) if used_fiberglass_sheets else 0} записей")
            print(f"   new_fiberglass_remainders: {len(new_fiberglass_remainders) if new_fiberglass_remainders else 0} записей")

            payload = {
                "grorders_mos_id": grorders_mos_id,
                "used_materials": used_materials or [],
                "business_remainders": business_remainders or [],
                "used_fiberglass_sheets": used_fiberglass_sheets or [],
                "new_fiberglass_remainders": new_fiberglass_remainders or []
            }
            
            print(f"🔧 API Client: Отправляем payload на сервер...")
            response = self.session.post(
                f"{self.base_url}/api/adjust-materials-altawin",
                json=payload,
                timeout=120
            )
            response.raise_for_status()
            result = response.json()
            print(f"✅ API Client: Получен ответ от сервера: {result}")
            return result
            
        except requests.RequestException as e:
            raise Exception(f"Ошибка корректировки материалов: {str(e)}")

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