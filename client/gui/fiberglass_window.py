"""
Окно оптимизации фибергласса
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QGroupBox, QTabWidget, QFormLayout,
    QSpinBox, QDoubleSpinBox, QCheckBox, QTextEdit, QSplitter, QHeaderView,
    QMessageBox, QProgressBar, QFrame, QComboBox, QApplication
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, QMutex
from PyQt5.QtGui import QFont, QIcon
import sys
import requests
import json
import logging
from datetime import datetime

# Настройка логирования
logger = logging.getLogger(__name__)

class FiberglassDataLoadThread(QThread):
    """Поток для загрузки данных фибергласса из API"""
    
    # Сигналы
    debug_step = pyqtSignal(str)
    error_occurred = pyqtSignal(str, str)  # title, message
    data_loaded = pyqtSignal(dict)  # loaded_data
    finished_loading = pyqtSignal()
    
    def __init__(self, grorder_mos_id, api_base_url="http://localhost:8001"):
        super().__init__()
        self.grorder_mos_id = grorder_mos_id
        self.api_base_url = api_base_url
        self.mutex = QMutex()
    
    def run(self):
        """Загрузка данных фибергласса"""
        try:
            self.debug_step.emit(f"🔄 Загружаю данные фибергласса для grorder_mos_id={self.grorder_mos_id}...")
            
            # Формируем запрос
            url = f"{self.api_base_url}/api/fiberglass/load-data"
            payload = {"grorder_mos_id": self.grorder_mos_id}
            
            # Отправляем запрос
            response = requests.post(url, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                self.debug_step.emit(f"✅ Данные загружены:")
                self.debug_step.emit(f"   - Деталей: {data.get('total_details', 0)}")
                self.debug_step.emit(f"   - Цельных рулонов: {data.get('total_materials', 0)}")
                self.debug_step.emit(f"   - Деловых остатков: {data.get('total_remainders', 0)}")
                
                self.data_loaded.emit(data)
                
            else:
                error_msg = f"Ошибка API: {response.status_code} - {response.text}"
                self.error_occurred.emit("Ошибка загрузки", error_msg)
                
        except requests.exceptions.ConnectionError:
            self.error_occurred.emit("Ошибка соединения", "Не удается подключиться к API серверу")
        except requests.exceptions.Timeout:
            self.error_occurred.emit("Таймаут", "Превышено время ожидания ответа от сервера")
        except Exception as e:
            self.error_occurred.emit("Ошибка", str(e))
        finally:
            self.finished_loading.emit()

class FiberglassOptimizationWindow(QWidget):
    """Окно оптимизации фибергласса"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.current_data = None
        self.load_thread = None
        
        self.setup_ui()
        self.setup_connections()
        
    def setup_ui(self):
        """Настройка интерфейса"""
        self.setWindowTitle("Оптимизация раскроя фибергласса")
        self.setGeometry(100, 100, 1400, 800)
        
        # Основной layout
        main_layout = QVBoxLayout(self)
        
        # === ПАНЕЛЬ УПРАВЛЕНИЯ ===
        control_panel = self.create_control_panel()
        main_layout.addWidget(control_panel)
        
        # === ОСНОВНЫЕ ДАННЫЕ ===
        data_splitter = QSplitter(Qt.Horizontal)
        
        # Левая панель - данные
        left_panel = self.create_data_panel()
        data_splitter.addWidget(left_panel)
        
        # Правая панель - настройки и результаты
        right_panel = self.create_results_panel()
        data_splitter.addWidget(right_panel)
        
        data_splitter.setSizes([800, 600])
        main_layout.addWidget(data_splitter)
        
        # === СТАТУС БАР ===
        self.status_label = QLabel("Готов к работе")
        main_layout.addWidget(self.status_label)
        
    def create_control_panel(self):
        """Создание панели управления"""
        group = QGroupBox("Загрузка данных")
        layout = QHBoxLayout(group)
        
        # Поле ввода grorder_mos_id
        layout.addWidget(QLabel("GRORDER_MOS_ID:"))
        self.grorder_mos_id_input = QLineEdit()
        self.grorder_mos_id_input.setPlaceholderText("Введите ID сменного задания...")
        layout.addWidget(self.grorder_mos_id_input)
        
        # Кнопка загрузки
        self.load_btn = QPushButton("Загрузить данные")
        self.load_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; }")
        layout.addWidget(self.load_btn)
        
        # Кнопка оптимизации
        self.optimize_btn = QPushButton("Оптимизировать")
        self.optimize_btn.setEnabled(False)
        self.optimize_btn.setStyleSheet("QPushButton { background-color: #2196F3; color: white; font-weight: bold; }")
        layout.addWidget(self.optimize_btn)
        
        # Кнопка экспорта PDF
        self.export_pdf_btn = QPushButton("Экспорт PDF")
        self.export_pdf_btn.setEnabled(False)
        self.export_pdf_btn.setStyleSheet("QPushButton { background-color: #FF9800; color: white; font-weight: bold; }")
        layout.addWidget(self.export_pdf_btn)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        return group
        
    def create_data_panel(self):
        """Создание панели данных"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Вкладки с данными
        self.data_tabs = QTabWidget()
        
        # Вкладка "Детали"
        self.details_table = self.create_details_table()
        self.data_tabs.addTab(self.details_table, "Детали для раскроя")
        
        # Вкладка "Цельные рулоны"
        self.materials_table = self.create_materials_table()
        self.data_tabs.addTab(self.materials_table, "Цельные рулоны")
        
        # Вкладка "Деловые остатки"
        self.remainders_table = self.create_remainders_table()
        self.data_tabs.addTab(self.remainders_table, "Деловые остатки")
        
        layout.addWidget(self.data_tabs)
        
        # Лог загрузки
        log_group = QGroupBox("Лог операций")
        log_layout = QVBoxLayout(log_group)
        
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(150)
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        
        layout.addWidget(log_group)
        
        return widget
        
    def create_results_panel(self):
        """Создание панели результатов"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Настройки оптимизации
        settings_group = self.create_optimization_settings()
        layout.addWidget(settings_group)
        
        # Результаты
        results_group = QGroupBox("Результаты оптимизации")
        results_layout = QVBoxLayout(results_group)
        
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setPlaceholderText("Результаты оптимизации появятся здесь...")
        results_layout.addWidget(self.results_text)
        
        layout.addWidget(results_group)
        
        return widget
        
    def create_optimization_settings(self):
        """Создание группы настроек оптимизации"""
        group = QGroupBox("Настройки оптимизации")
        layout = QFormLayout(group)
        
        # Отступы для листа
        layout.addRow(QLabel("=== Отступы для листа ==="))
        
        self.sheet_margin_top = QSpinBox()
        self.sheet_margin_top.setRange(0, 100)
        self.sheet_margin_top.setValue(15)
        self.sheet_margin_top.setSuffix(" мм")
        layout.addRow("Сверху:", self.sheet_margin_top)
        
        self.sheet_margin_bottom = QSpinBox()
        self.sheet_margin_bottom.setRange(0, 100)
        self.sheet_margin_bottom.setValue(15)
        self.sheet_margin_bottom.setSuffix(" мм")
        layout.addRow("Снизу:", self.sheet_margin_bottom)
        
        self.sheet_margin_left = QSpinBox()
        self.sheet_margin_left.setRange(0, 100)
        self.sheet_margin_left.setValue(15)
        self.sheet_margin_left.setSuffix(" мм")
        layout.addRow("Слева:", self.sheet_margin_left)
        
        self.sheet_margin_right = QSpinBox()
        self.sheet_margin_right.setRange(0, 100)
        self.sheet_margin_right.setValue(15)
        self.sheet_margin_right.setSuffix(" мм")
        layout.addRow("Справа:", self.sheet_margin_right)
        
        # Отступы для остатка
        layout.addRow(QLabel("=== Отступы для остатка ==="))
        
        self.remainder_margin_top = QSpinBox()
        self.remainder_margin_top.setRange(0, 100)
        self.remainder_margin_top.setValue(15)
        self.remainder_margin_top.setSuffix(" мм")
        layout.addRow("Сверху:", self.remainder_margin_top)
        
        self.remainder_margin_bottom = QSpinBox()
        self.remainder_margin_bottom.setRange(0, 100)
        self.remainder_margin_bottom.setValue(15)
        self.remainder_margin_bottom.setSuffix(" мм")
        layout.addRow("Снизу:", self.remainder_margin_bottom)
        
        self.remainder_margin_left = QSpinBox()
        self.remainder_margin_left.setRange(0, 100)
        self.remainder_margin_left.setValue(15)
        self.remainder_margin_left.setSuffix(" мм")
        layout.addRow("Слева:", self.remainder_margin_left)
        
        self.remainder_margin_right = QSpinBox()
        self.remainder_margin_right.setRange(0, 100)
        self.remainder_margin_right.setValue(15)
        self.remainder_margin_right.setSuffix(" мм")
        layout.addRow("Справа:", self.remainder_margin_right)
        
        # Другие параметры
        layout.addRow(QLabel("=== Общие параметры ==="))
        
        self.blade_width = QSpinBox()
        self.blade_width.setRange(0, 20)
        self.blade_width.setValue(1)
        self.blade_width.setSuffix(" мм")
        layout.addRow("Ширина ножа:", self.blade_width)
        
        self.max_waste_percent = QSpinBox()
        self.max_waste_percent.setRange(1, 50)
        self.max_waste_percent.setValue(5)
        self.max_waste_percent.setSuffix(" %")
        layout.addRow("Допустимый % отхода:", self.max_waste_percent)
        
        self.min_remainder_width = QSpinBox()
        self.min_remainder_width.setRange(100, 1000)
        self.min_remainder_width.setValue(500)
        self.min_remainder_width.setSuffix(" мм")
        layout.addRow("Мин. ширина остатка:", self.min_remainder_width)
        
        self.min_remainder_height = QSpinBox()
        self.min_remainder_height.setRange(100, 1000)
        self.min_remainder_height.setValue(500)
        self.min_remainder_height.setSuffix(" мм")
        layout.addRow("Мин. высота остатка:", self.min_remainder_height)
        
        self.use_simplified_optimization = QCheckBox("Использовать упрощенную оптимизацию")
        self.use_simplified_optimization.setChecked(True)
        layout.addRow(self.use_simplified_optimization)
        
        return group
        
    def create_details_table(self):
        """Создание таблицы деталей"""
        table = QTableWidget()
        
        headers = [
            "ID заказа", "Изделие", "Ширина (мм)", "Высота (мм)", 
            "Количество", "Модель №", "Проём", "Часть", "Материал"
        ]
        
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setStretchLastSection(True)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        
        return table
        
    def create_materials_table(self):
        """Создание таблицы цельных рулонов"""
        table = QTableWidget()
        
        headers = [
            "Материал", "Ширина (мм)", "Длина (мм)", 
            "Количество рулонов", "Площадь (м²)"
        ]
        
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setStretchLastSection(True)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        
        return table
        
    def create_remainders_table(self):
        """Создание таблицы деловых остатков"""
        table = QTableWidget()
        
        headers = [
            "Материал", "Ширина (мм)", "Высота (мм)", 
            "Количество", "Площадь (мм²)", "ID остатка"
        ]
        
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setStretchLastSection(True)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        
        return table
        
    def setup_connections(self):
        """Настройка соединений сигналов"""
        self.load_btn.clicked.connect(self.load_data)
        self.optimize_btn.clicked.connect(self.optimize_cutting)
        self.export_pdf_btn.clicked.connect(self.export_pdf)
        
    def load_data(self):
        """Загрузка данных фибергласса"""
        grorder_mos_id_text = self.grorder_mos_id_input.text().strip()
        
        if not grorder_mos_id_text:
            QMessageBox.warning(self, "Ошибка", "Введите GRORDER_MOS_ID")
            return
            
        try:
            grorder_mos_id = int(grorder_mos_id_text)
        except ValueError:
            QMessageBox.warning(self, "Ошибка", "GRORDER_MOS_ID должен быть числом")
            return
            
        # Показываем progress bar
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Индикатор загрузки
        
        # Отключаем кнопки
        self.load_btn.setEnabled(False)
        self.optimize_btn.setEnabled(False)
        self.export_pdf_btn.setEnabled(False)
        
        # Очищаем лог
        self.log_text.clear()
        
        # Запускаем поток загрузки
        self.load_thread = FiberglassDataLoadThread(grorder_mos_id)
        self.load_thread.debug_step.connect(self.add_log_message)
        self.load_thread.error_occurred.connect(self.show_error)
        self.load_thread.data_loaded.connect(self.on_data_loaded)
        self.load_thread.finished_loading.connect(self.on_loading_finished)
        self.load_thread.start()
        
    def add_log_message(self, message):
        """Добавление сообщения в лог"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        
        # Прокручиваем к концу
        cursor = self.log_text.textCursor()
        cursor.movePosition(cursor.End)
        self.log_text.setTextCursor(cursor)
        
    def show_error(self, title, message):
        """Показать ошибку"""
        QMessageBox.critical(self, title, message)
        self.add_log_message(f"❌ {title}: {message}")
        
    def on_data_loaded(self, data):
        """Обработка загруженных данных"""
        self.current_data = data
        
        # Заполняем таблицы
        self.fill_details_table(data.get("details", []))
        self.fill_materials_table(data.get("materials", []))
        self.fill_remainders_table(data.get("remainders", []))
        
        # Активируем кнопку оптимизации
        self.optimize_btn.setEnabled(True)
        
        self.add_log_message("✅ Данные успешно загружены и отображены")
        
    def on_loading_finished(self):
        """Завершение загрузки"""
        self.progress_bar.setVisible(False)
        self.load_btn.setEnabled(True)
        
    def fill_details_table(self, details):
        """Заполнение таблицы деталей"""
        table = self.details_table
        table.setRowCount(len(details))
        
        for row, detail in enumerate(details):
            table.setItem(row, 0, QTableWidgetItem(str(detail.get("orderid", ""))))
            table.setItem(row, 1, QTableWidgetItem(detail.get("item_name", "")))
            table.setItem(row, 2, QTableWidgetItem(f"{detail.get('width', 0):.1f}"))
            table.setItem(row, 3, QTableWidgetItem(f"{detail.get('height', 0):.1f}"))
            table.setItem(row, 4, QTableWidgetItem(str(detail.get("quantity", 0))))
            table.setItem(row, 5, QTableWidgetItem(str(detail.get("modelno", "") or "")))
            table.setItem(row, 6, QTableWidgetItem(detail.get("partside", "") or ""))
            table.setItem(row, 7, QTableWidgetItem(detail.get("izdpart", "") or ""))
            table.setItem(row, 8, QTableWidgetItem(detail.get("marking", "")))
            
        # Автоматическая подгонка колонок
        table.resizeColumnsToContents()
        
    def fill_materials_table(self, materials):
        """Заполнение таблицы цельных рулонов"""
        table = self.materials_table
        table.setRowCount(len(materials))
        
        for row, material in enumerate(materials):
            width = material.get("width", 0)
            height = material.get("height", 0)
            quantity = material.get("quantity", 0)
            area_m2 = (width * height * quantity) / 1_000_000  # Перевод в м²
            
            table.setItem(row, 0, QTableWidgetItem(material.get("marking", "")))
            table.setItem(row, 1, QTableWidgetItem(f"{width:.0f}"))
            table.setItem(row, 2, QTableWidgetItem(f"{height:.0f}"))
            table.setItem(row, 3, QTableWidgetItem(str(quantity)))
            table.setItem(row, 4, QTableWidgetItem(f"{area_m2:.2f}"))
            
        table.resizeColumnsToContents()
        
    def fill_remainders_table(self, remainders):
        """Заполнение таблицы деловых остатков"""
        table = self.remainders_table
        table.setRowCount(len(remainders))
        
        for row, remainder in enumerate(remainders):
            table.setItem(row, 0, QTableWidgetItem(remainder.get("marking", "")))
            table.setItem(row, 1, QTableWidgetItem(f"{remainder.get('width', 0):.0f}"))
            table.setItem(row, 2, QTableWidgetItem(f"{remainder.get('height', 0):.0f}"))
            table.setItem(row, 3, QTableWidgetItem(str(remainder.get("quantity", 0))))
            table.setItem(row, 4, QTableWidgetItem(f"{remainder.get('area_mm2', 0):.0f}"))
            table.setItem(row, 5, QTableWidgetItem(str(remainder.get("remainder_id", "") or "")))
            
        table.resizeColumnsToContents()
        
    def optimize_cutting(self):
        """Запуск оптимизации раскроя"""
        if not self.current_data:
            QMessageBox.warning(self, "Ошибка", "Сначала загрузите данные")
            return
            
        # TODO: Реализовать вызов алгоритма оптимизации
        self.add_log_message("🔄 Запуск оптимизации раскроя...")
        self.results_text.setText("Оптимизация в разработке...")
        
        # Активируем кнопку экспорта
        self.export_pdf_btn.setEnabled(True)
        
    def export_pdf(self):
        """Экспорт результатов в PDF"""
        # TODO: Реализовать экспорт в PDF
        self.add_log_message("📄 Экспорт в PDF...")
        QMessageBox.information(self, "Экспорт PDF", "Функция экспорта в разработке")
        
    def get_optimization_settings(self):
        """Получить настройки оптимизации"""
        return {
            "sheet_margin_top": self.sheet_margin_top.value(),
            "sheet_margin_bottom": self.sheet_margin_bottom.value(),
            "sheet_margin_left": self.sheet_margin_left.value(),
            "sheet_margin_right": self.sheet_margin_right.value(),
            "remainder_margin_top": self.remainder_margin_top.value(),
            "remainder_margin_bottom": self.remainder_margin_bottom.value(),
            "remainder_margin_left": self.remainder_margin_left.value(),
            "remainder_margin_right": self.remainder_margin_right.value(),
            "blade_width": self.blade_width.value(),
            "max_waste_percent": self.max_waste_percent.value(),
            "min_remainder_width": self.min_remainder_width.value(),
            "min_remainder_height": self.min_remainder_height.value(),
            "use_simplified_optimization": self.use_simplified_optimization.isChecked()
        }

def main():
    """Тестовый запуск окна"""
    app = QApplication(sys.argv)
    
    window = FiberglassOptimizationWindow()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
