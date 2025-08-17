#!/usr/bin/env python3
"""
Тестовый скрипт для проверки API endpoints MOS таблиц
"""

import requests
import json

# Настройки API
BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api"

def test_connection():
    """Тест соединения с API"""
    try:
        response = requests.get(f"{API_BASE}/test-connection", timeout=10)
        print(f"🔧 Тест соединения: HTTP {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Соединение: {data}")
            return True
        else:
            print(f"❌ Ошибка соединения: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Ошибка теста соединения: {e}")
        return False

def test_create_optimized_mos():
    """Тест создания записи в OPTIMIZED_MOS"""
    try:
        payload = {
            "grorder_mos_id": 999,  # Тестовый ID
            "goodsid": 123,         # Тестовый goodsid
            "qty": 1,
            "isbar": 0,
            "longprof": 6000.0,
            "cutwidth": 5,
            "border": 0,
            "minrest": 300,
            "mintrash": 50,
            "map": "1000.0;2000.0;3000.0",
            "ostat": 0.0,
            "sumprof": 6000.0,
            "restpercent": 0.0,
            "trashpercent": 0.0,
            "beginindent": 0,
            "endindent": 0,
            "sumtrash": 0.0,
        }
        
        print(f"🔧 Тест создания OPTIMIZED_MOS: {json.dumps(payload, indent=2)}")
        
        response = requests.post(
            f"{API_BASE}/optimized-mos",
            json=payload,
            timeout=30
        )
        
        print(f"🔧 Ответ: HTTP {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ OPTIMIZED_MOS создан: {data}")
            return data.get('id')
        else:
            print(f"❌ Ошибка создания OPTIMIZED_MOS: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Ошибка теста создания OPTIMIZED_MOS: {e}")
        return None

def test_create_optdetail_mos(optimized_mos_id):
    """Тест создания записи в OPTDETAIL_MOS"""
    if not optimized_mos_id:
        print("❌ Нет ID для OPTIMIZED_MOS, пропускаем тест OPTDETAIL_MOS")
        return None
        
    try:
        payload = {
            "optimized_mos_id": optimized_mos_id,
            "orderid": 456,  # Тестовый orderid
            "qty": 1,
            "itemsdetailid": None,
            "itemlong": 1000.0,
            "ug1": None,
            "ug2": None,
            "num": 1,
            "subnum": 1,
            "long_al": 1005.0,
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
            "flugelopentag": None
        }
        
        print(f"🔧 Тест создания OPTDETAIL_MOS: {json.dumps(payload, indent=2)}")
        
        response = requests.post(
            f"{API_BASE}/optdetail-mos",
            json=payload,
            timeout=30
        )
        
        print(f"🔧 Ответ: HTTP {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ OPTDETAIL_MOS создан: {data}")
            return data.get('id')
        else:
            print(f"❌ Ошибка создания OPTDETAIL_MOS: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Ошибка теста создания OPTDETAIL_MOS: {e}")
        return None

def test_delete_optimized_mos(grorders_mos_id):
    """Тест удаления записей MOS"""
    try:
        print(f"🔧 Тест удаления данных MOS для grorders_mos_id={grorders_mos_id}")
        
        response = requests.delete(
            f"{API_BASE}/optimized-mos/by-grorders-mos-id/{grorders_mos_id}",
            timeout=30
        )
        
        print(f"🔧 Ответ: HTTP {response.status_code}")
        if response.status_code in [200, 404]:
            data = response.json() if response.content else {}
            print(f"✅ Данные MOS удалены: {data}")
            return True
        else:
            print(f"❌ Ошибка удаления данных MOS: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка теста удаления данных MOS: {e}")
        return False

def main():
    """Основная функция тестирования"""
    print("🧪 Начало тестирования API endpoints MOS таблиц")
    print("=" * 60)
    
    # Тест 1: Проверка соединения
    print("\n1️⃣ Тест соединения с API")
    if not test_connection():
        print("❌ Не удалось подключиться к API, завершаем тестирование")
        return
    
    # Тест 2: Создание OPTIMIZED_MOS
    print("\n2️⃣ Тест создания записи в OPTIMIZED_MOS")
    optimized_mos_id = test_create_optimized_mos()
    
    # Тест 3: Создание OPTDETAIL_MOS
    print("\n3️⃣ Тест создания записи в OPTDETAIL_MOS")
    optdetail_mos_id = test_create_optdetail_mos(optimized_mos_id)
    
    # Тест 4: Удаление тестовых данных
    print("\n4️⃣ Тест удаления тестовых данных")
    test_delete_optimized_mos(999)
    
    print("\n" + "=" * 60)
    print("🏁 Тестирование завершено")
    
    if optimized_mos_id and optdetail_mos_id:
        print("✅ Все тесты прошли успешно!")
    else:
        print("❌ Некоторые тесты не прошли")

if __name__ == "__main__":
    main()
