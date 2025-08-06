"""
Linear Optimizer Client
Приложение для оптимизации линейного распила профилей
"""

import sys
import os

# Добавляем текущую папку в путь для импортов
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    """Главная функция запуска приложения"""
    
    print("🚀 Запуск Linear Optimizer Client...")
    
    # Проверяем что мы в правильной директории
    script_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"📁 Рабочая директория: {script_dir}")
    
    try:
        print("📦 Импортирование PyQt5...")
        from PyQt5.QtWidgets import QApplication, QMessageBox
        print("✅ PyQt5 импортирован успешно")
        
        print("📦 Импортирование главного окна...")
        from gui.main_window import LinearOptimizerWindow
        print("✅ Главное окно импортировано успешно")
        
        print("🎯 Создание приложения...")
        # Создание приложения
        app = QApplication(sys.argv)
        app.setApplicationName("Linear Optimizer")
        app.setOrganizationName("YourCompany")
        
        print("🖥️  Создание главного окна...")
        # Создание и отображение главного окна
        window = LinearOptimizerWindow()
        print("✅ Главное окно создано успешно")
        
        # Если передан ID заказа через командную строку
        if len(sys.argv) > 1:
            try:
                order_id = int(sys.argv[1])
                print(f"📋 Установка ID заказа: {order_id}")
                window.set_order_id(order_id)
            except ValueError:
                print("⚠️  Неверный формат ID заказа в аргументах")
        
        print("📺 Показ окна...")
        # Запуск в максимизированном окне
        window.showMaximized()
        
        print("▶️  Запуск приложения...")
        # Запуск приложения
        sys.exit(app.exec_())
        
    except ImportError as e:
        error_msg = f"Ошибка импорта: {e}"
        print(f"❌ {error_msg}")
        print("💡 Возможные решения:")
        print("   1. Установите зависимости: pip install -r requirements.txt")
        print("   2. Активируйте виртуальное окружение")
        print("   3. Проверьте, что PyQt5 установлен: pip install PyQt5")
        
        # Показываем MessageBox если возможно
        try:
            from PyQt5.QtWidgets import QApplication, QMessageBox
            app = QApplication([])
            QMessageBox.critical(None, "Ошибка запуска", error_msg + 
                               "\n\nУстановите зависимости:\npip install -r requirements.txt")
        except:
            pass
            
        sys.exit(1)
        
    except Exception as e:
        error_msg = f"Критическая ошибка: {e}"
        print(f"❌ {error_msg}")
        print("📋 Подробности ошибки:")
        import traceback
        traceback.print_exc()
        
        # Показываем MessageBox если возможно
        try:
            from PyQt5.QtWidgets import QApplication, QMessageBox
            app = QApplication([])
            QMessageBox.critical(None, "Критическая ошибка", 
                               error_msg + "\n\nПроверьте консоль для подробностей")
        except:
            pass
            
        print("\n💡 Попробуйте:")
        print("   1. Запустить тест компонентов: python test_components.py")
        print("   2. Проверить, что API сервер запущен")
        print("   3. Переустановить зависимости")
        
        sys.exit(1)

if __name__ == "__main__":
    main()