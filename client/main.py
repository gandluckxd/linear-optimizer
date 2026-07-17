"""
Interactive Linear Optimizer Client.

The unattended entry point is ``mos_optimizer_runner.py``.  This file remains
for diagnostics and backwards-compatible manual work with the existing GUI.
"""

import os
import sys


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    print("🚀 Запуск Linear Optimizer Client...")
    try:
        from PyQt5.QtWidgets import QApplication, QMessageBox
        from gui.main_window import LinearOptimizerWindow

        app = QApplication(sys.argv)
        app.setApplicationName("Linear Optimizer")
        app.setOrganizationName("YourCompany")
        window = LinearOptimizerWindow()
        if len(sys.argv) > 1:
            try:
                window.set_order_id(int(sys.argv[1]))
            except ValueError:
                print("⚠️  Неверный формат ID")
        window.showMaximized()
        sys.exit(app.exec_())
    except ImportError as error:
        print(f"❌ Ошибка импорта: {error}")
        try:
            app = QApplication([])
            QMessageBox.critical(None, "Ошибка запуска", str(error))
        except Exception:
            pass
        sys.exit(1)
    except Exception as error:
        print(f"❌ Критическая ошибка: {error}")
        raise


if __name__ == "__main__":
    main()
