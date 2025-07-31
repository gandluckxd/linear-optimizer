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
    try:
        from PyQt5.QtWidgets import QApplication
        from gui.main_window import LinearOptimizerWindow
        
        # Создание приложения
        app = QApplication(sys.argv)
        app.setApplicationName("Linear Optimizer")
        app.setOrganizationName("YourCompany")
        
        # Создание и отображение главного окна
        window = LinearOptimizerWindow()
        
        # Если передан ID заказа через командную строку
        if len(sys.argv) > 1:
            try:
                order_id = int(sys.argv[1])
                window.set_order_id(order_id)
            except ValueError:
                pass
        
        # Запуск в максимизированном окне
        window.showMaximized()
        
        # Запуск приложения
        sys.exit(app.exec_())
        
    except ImportError as e:
        print(f"Ошибка импорта: {e}")
        print("Убедитесь, что установлены все зависимости: pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()