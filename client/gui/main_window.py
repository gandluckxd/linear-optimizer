"""
Главное окно Linear Optimizer
Профессиональная система оптимизации линейного распила
Адаптировано из Glass Optimizer
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QTableWidget, QTableWidgetItem, QCheckBox, QSpinBox, QGroupBox,
    QPushButton, QFormLayout, QLineEdit,
    QTabWidget, QComboBox, QDialog, QProgressBar, QMessageBox, QHeaderView,
    QSplitter, QFrame, QTextEdit, QSlider, QMainWindow, QMenuBar, QStatusBar,
    QAction, QApplication, QFileDialog, QScrollArea, QGraphicsScene, QGraphicsView
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt5.QtGui import QFont, QIcon, QShowEvent, QPixmap, QPainter
import sys
# import threading  # Убрали - теперь используем QThread
from datetime import datetime
import functools
import requests
import os
import json
import logging
from typing import Dict


# Импорты для модульной архитектуры
from core.api_client import get_api_client
from core.optimizer import LinearOptimizer, CuttingStockOptimizer, OptimizationSettings, SolverType
from core.headless_workflow import (
    build_stocks,
    generate_cell_map,
    load_optimization_input,
    optimize_fiberglass_collections,
    optimize_linear,
)

from core.models import Profile, Stock, OptimizationResult, StockRemainder, StockMaterial, FiberglassDetail, FiberglassSheet
from .table_widgets import (
    _create_text_item, _create_numeric_item, setup_table_columns,
    fill_profiles_table, fill_stock_table, fill_optimization_results_table,
    fill_stock_remainders_table, fill_stock_materials_table, fill_fabric_details_table,
    fill_fabric_remainders_table, fill_fabric_materials_table,
    update_table_column_widths, clear_table, enable_table_sorting,
    copy_table_to_clipboard, copy_table_as_csv
)
from .dialogs import DebugDialog, ProgressDialog, OptimizationSettingsDialog, ApiSettingsDialog

from .config import MAIN_WINDOW_STYLE, TAB_STYLE, SPECIAL_BUTTON_STYLES, WIDGET_CONFIGS, COLORS
from .visualization_tab import VisualizationTab

# Настройка логирования
logger = logging.getLogger(__name__)


class DataLoadThread(QThread):
    """Поток для загрузки данных из API"""
    
    # Сигналы для коммуникации с главным потоком
    debug_step = pyqtSignal(str)
    error_occurred = pyqtSignal(str, str, str)  # title, message, icon
    success_occurred = pyqtSignal()
    data_loaded = pyqtSignal(list, dict, list, dict)  # profiles, stock_data, fabric_details, fabric_stock_data
    finished_loading = pyqtSignal()
    
    def __init__(self, api_client, order_ids, grorders_mos_id=None):
        super().__init__()
        self.api_client = api_client
        self.order_ids = order_ids if isinstance(order_ids, list) else [order_ids]
        self.grorders_mos_id = grorders_mos_id
    
    def run(self):
        """Основная логика загрузки данных"""
        try:
            if not self.grorders_mos_id:
                raise ValueError("Не задан grorders_mos_id")
            loaded = load_optimization_input(
                self.api_client,
                self.grorders_mos_id,
                progress=self.debug_step.emit,
            )
            self.data_loaded.emit(
                loaded.profiles,
                {'remainders': loaded.stock_remainders, 'materials': loaded.stock_materials},
                loaded.fabric_details,
                {'remainders': loaded.fabric_remainders, 'materials': loaded.fabric_materials}
            )
            self.debug_step.emit("🎉 Загрузка данных завершена успешно!")
            self.success_occurred.emit()
            
        except Exception as e:
            self.debug_step.emit(f"❌ Ошибка загрузки: {e}")
            self.error_occurred.emit("Ошибка загрузки", str(e), "critical")
        finally:
            self.finished_loading.emit()


class OptimizationThread(QThread):
    """Поток для выполнения оптимизации"""
    
    # Сигналы для коммуникации с главным потоком
    debug_step = pyqtSignal(str)
    optimization_result = pyqtSignal(object)  # OptimizationResult
    optimization_error = pyqtSignal(str)
    progress_updated = pyqtSignal(int)  # процент выполнения
    finished_optimization = pyqtSignal()
    
    def __init__(self, optimizer, profiles, stocks, settings):
        super().__init__()
        self.optimizer = optimizer
        self.profiles = profiles
        self.stocks = stocks
        self.settings = settings
    
    def run(self):
        """Основная логика оптимизации"""
        try:
            self.debug_step.emit("🔧 DEBUG: Поток оптимизации запущен")
            
            def progress_callback(percent):
                """Коллбэк для обновления прогресса"""
                self.progress_updated.emit(int(percent))
                self.debug_step.emit(f"🔧 DEBUG: Прогресс {percent}%")
            
            # Проверяем данные
            if not self.profiles:
                self.optimization_error.emit("Нет профилей для оптимизации")
                return
                
            if not self.stocks:
                self.optimization_error.emit("Нет хлыстов для оптимизации")
                return
            
            self.debug_step.emit("🔧 DEBUG: Вызываем общий workflow оптимизации")
            
            # Запуск оптимизации
            result = optimize_linear(
                self.profiles,
                self.stocks,
                self.settings,
                progress_callback,
            )
            
            self.debug_step.emit(f"🔧 DEBUG: Оптимизация завершена, результат: {result}")
            
            if result and result.success:
                self.optimization_result.emit(result)
                self.debug_step.emit(f"✅ Оптимизация успешна: {len(result.cut_plans)} планов")
            else:
                error_msg = "Оптимизация не дала результатов"
                if result and hasattr(result, 'message'):
                    error_msg = result.message
                self.debug_step.emit(f"❌ Оптимизация неуспешна: {error_msg}")
                self.optimization_error.emit(error_msg)
                
        except Exception as e:
            import traceback
            error_msg = f"Ошибка оптимизации: {str(e)}"
            self.debug_step.emit(f"❌ Исключение в оптимизации: {error_msg}")
            self.debug_step.emit(f"❌ Трассировка: {traceback.format_exc()}")
            self.optimization_error.emit(error_msg)
        finally:
            self.debug_step.emit("🔧 DEBUG: Закрываем диалог прогресса")
            self.finished_optimization.emit()


class LinearOptimizerWindow(QMainWindow):
    """Главное окно приложения Linear Optimizer"""
    
    # Сигналы для thread-safe коммуникации
    debug_step_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str, str, str)  # title, message, icon
    success_signal = pyqtSignal()
    data_loaded_signal = pyqtSignal(list, dict, list, dict)  # profiles, stock_data, fabric_details, fabric_stock_data
    restore_button_signal = pyqtSignal()
    
    # Сигналы для оптимизации
    optimization_result_signal = pyqtSignal(object)  # OptimizationResult
    optimization_error_signal = pyqtSignal(str)
    close_progress_signal = pyqtSignal()

    # Сигналы для обновления визуализации
    update_visualization_signal = pyqtSignal(object)  # FiberglassOptimizationResult
    
    def __init__(self):
        super().__init__()
        
        # Инициализация данных
        self.api_client = get_api_client()
        self.optimizer = LinearOptimizer()
        self.current_order_id = None
        self.profiles = []
        self.stocks = []  # Для обратной совместимости
        self.stock_remainders = []  # Остатки профилей со склада
        self.stock_materials = []   # Цельные материалы профилей со склада
        self.fabric_details = []    # Детали полотен для раскроя
        self.fabric_remainders = [] # Остатки полотен со склада
        self.fabric_materials = []  # Цельные материалы полотен со склада
        self.optimization_result = None
        self.fabric_optimization_result = None  # Результаты оптимизации фибергласса

        self.current_settings = OptimizationSettings()


        
        # Инициализация параметров оптимизации (значения по умолчанию)
        self.optimization_params = {
            'blade_width': 5,
            'min_remainder_length': 300,
            'max_waste_percent': 15,
            'pair_optimization': True,
            'use_remainders': True,
            'min_trash_mm': 50,
            'begin_indent': 10,
            'end_indent': 10,
            # Параметры парной оптимизации
            'pairing_exact_bonus': 3000.0,
            'pairing_partial_bonus': 1000.0,
            'pairing_partial_threshold': 0.7,
            'pairing_new_simple_bonus': 150.0,
            # Параметры фибергласса
            'planar_min_remainder_width': 500.0,
            'planar_min_remainder_height': 500.0,
            'planar_cut_width': 1.0,
            'sheet_indent': 15.0,
            'remainder_indent': 15.0,
            'planar_max_waste_percent': 5.0,
            'use_warehouse_remnants': True,
            'allow_rotation': True
        }
        
        # Инициализация диалогов
        self.debug_dialog = None
        self.progress_dialog = None
        
        # Инициализация потоков
        self.data_load_thread = None
        self.optimization_thread = None
        
        # Настройка UI
        self.init_ui()
        
        # Настройка размера окна
        self.setWindowTitle("Linear Optimizer - Система оптимизации линейного распила")
        self.setMinimumSize(1400, 900)
        
        # Подключение сигналов для thread-safe коммуникации
        self.debug_step_signal.connect(self._add_debug_step_safe)
        self.error_signal.connect(self._show_error_safe)
        self.success_signal.connect(self._show_success_safe)
        self.data_loaded_signal.connect(self._update_tables_safe)
        self.restore_button_signal.connect(self._restore_button_safe)
        
        # Сигналы для оптимизации
        self.optimization_result_signal.connect(self._handle_optimization_result)
        self.optimization_error_signal.connect(self._handle_optimization_error)
        self.close_progress_signal.connect(self._close_progress_dialog)

        # Сигналы для обновления визуализации
        self.update_visualization_signal.connect(self._update_visualization_tab)
        
        print("🔧 DEBUG: Главное окно Linear Optimizer инициализировано")

    def showEvent(self, event):
        """Переопределение showEvent для настройки темного заголовка"""
        super().showEvent(event)
        
        # Настройка темного заголовка окна (для Windows)
        try:
            import ctypes
            from ctypes import wintypes
            import platform
            
            # Получаем handle окна
            hwnd = int(self.winId())
            
            # Определяем версию Windows и используем соответствующую константу
            version = platform.version()
            version_parts = version.split('.')
            build_number = int(version_parts[2]) if len(version_parts) > 2 else 0
            
            # Для Windows 10 1903+ (build 18362+) и Windows 11
            if build_number >= 18362:
                # Пробуем новую константу (Windows 11)
                DWMWA_USE_IMMERSIVE_DARK_MODE = 20
                value = ctypes.c_int(1)
                result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, 
                    ctypes.byref(value), ctypes.sizeof(value)
                )
                
                # Если не сработало, пробуем старую константу
                if result != 0:
                    DWMWA_USE_IMMERSIVE_DARK_MODE = 19
                    result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, 
                        ctypes.byref(value), ctypes.sizeof(value)
                    )
                
                if result == 0:
                    print(f"🔧 DEBUG: Темный заголовок окна установлен (константа {DWMWA_USE_IMMERSIVE_DARK_MODE})")
                else:
                    print(f"🔧 DEBUG: Не удалось установить темный заголовок (код ошибки: {result})")
            else:
                print("🔧 DEBUG: Версия Windows не поддерживает темные заголовки окон")
                
        except Exception as e:
            # Если не получилось (не Windows или ошибка), продолжаем без темного заголовка
            print(f"🔧 DEBUG: Не удалось установить темный заголовок: {e}")
            pass

    def init_ui(self):
        """Инициализация интерфейса"""
        # Применение темной темы ко всему приложению
        self.setStyleSheet(MAIN_WINDOW_STYLE)
        
        # Создание меню
        self.create_menu()
        
        # Создание центрального виджета
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Создание вкладок
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(TAB_STYLE)
        
        # Вкладка 1: Данные заказа
        self.create_order_data_tab()
        
        # Вкладка 2: Результаты оптимизации
        self.create_results_tab()

        # Вкладка 3: Визуализация раскроя
        self.create_visualization_tab()



        main_layout.addWidget(self.tabs)
        
        # Статус бар
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Готов к работе")

    def create_menu(self):
        """Создание меню приложения"""
        menubar = self.menuBar()
        
        # Меню Файл
        file_menu = menubar.addMenu("Файл")
        
        new_action = QAction("Новая оптимизация", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self.new_optimization)
        file_menu.addAction(new_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Выход", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Меню Параметры
        params_menu = menubar.addMenu("Параметры")
        
        optimization_params_action = QAction("Параметры оптимизации", self)
        optimization_params_action.setShortcut("Ctrl+P")
        optimization_params_action.triggered.connect(self.show_optimization_settings)
        params_menu.addAction(optimization_params_action)
        
        # Меню Настройки
        settings_menu = menubar.addMenu("Настройки")
        
        api_settings_action = QAction("Настройки API", self)
        api_settings_action.triggered.connect(self.show_api_settings)
        settings_menu.addAction(api_settings_action)



    def create_order_data_tab(self):
        """Создание вкладки данных заказа"""
        order_tab = QWidget()
        layout = QVBoxLayout(order_tab)

        # Верхняя часть - информация о заказе
        top_group = self.create_order_info_group()
        layout.addWidget(top_group)
        
        # Средняя часть - данные (профили и полотна)
        middle_splitter = QSplitter(Qt.Horizontal)
        
        # Левая часть - профили
        left_group = self.create_profiles_section()
        middle_splitter.addWidget(left_group)
        
        # Правая часть - полотна
        right_group = self.create_fabric_section()
        middle_splitter.addWidget(right_group)
        
        middle_splitter.setSizes([500, 900])
        layout.addWidget(middle_splitter)
        
        # Кнопка оптимизации
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        self.optimize_button = QPushButton("🚀 Запустить оптимизацию")
        self.optimize_button.clicked.connect(self.on_optimize_clicked)
        self.optimize_button.setEnabled(False)
        self.optimize_button.setStyleSheet(SPECIAL_BUTTON_STYLES["optimize"])
        buttons_layout.addWidget(self.optimize_button)

        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)
        
        self.tabs.addTab(order_tab, "📊 Данные заказа")

    def create_order_info_group(self):
        """Создание группы информации о заказе"""
        group = QGroupBox("Информация о заказе")
        layout = QVBoxLayout(group)

        # Поля ввода и загрузки
        input_layout = QHBoxLayout()
        
        input_layout.addWidget(QLabel("Идентификатор сменного задания москитных сеток:"))
        self.order_id_input = QLineEdit()
        self.order_id_input.setPlaceholderText("Введите grorders_mos_id (целое число)")
        self.order_id_input.setMinimumWidth(300)
        self.order_id_input.setMaximumWidth(400)
        input_layout.addWidget(self.order_id_input)
        
        self.load_data_button = QPushButton("Загрузить данные")
        self.load_data_button.clicked.connect(self.on_load_data_clicked)
        input_layout.addWidget(self.load_data_button)
        
        input_layout.addStretch()
        
        # Информация о заказе
        self.order_info_label = QLabel("<заказ не загружен>")
        self.order_info_label.setStyleSheet(WIDGET_CONFIGS["info_label"])
        input_layout.addWidget(self.order_info_label)
        
        layout.addLayout(input_layout)
        
        return group

    def create_profiles_section(self):
        """Создание раздела профилей (профили + склады профилей)"""
        main_widget = QWidget()
        layout = QVBoxLayout(main_widget)
        
        # Группа профилей для распила
        profiles_group = QGroupBox("Профили для распила")
        profiles_layout = QVBoxLayout(profiles_group)
        
        # Таблица профилей
        self.profiles_table = QTableWidget()
        setup_table_columns(self.profiles_table, [
            'Элемент', 'Артикул профиля', 'Длина (мм)', 'Количество'
        ])
        
        # Включаем сортировку
        enable_table_sorting(self.profiles_table, True)
        self.profiles_table.setMinimumHeight(200)
        profiles_layout.addWidget(self.profiles_table)
        
        # Создаем вертикальный сплиттер для двух таблиц складов профилей
        splitter = QSplitter(Qt.Vertical)
        
        # Группа остатков профилей на складе
        remainders_group = QGroupBox("Склад остатков профилей")
        remainders_layout = QVBoxLayout(remainders_group)
        
        self.stock_remainders_table = QTableWidget()
        setup_table_columns(self.stock_remainders_table, [
            'Наименование', 'Длина (мм)', 'Количество палок'
        ])
        enable_table_sorting(self.stock_remainders_table, True)
        self.stock_remainders_table.setMinimumHeight(150)
        remainders_layout.addWidget(self.stock_remainders_table)
        
        # Группа материалов профилей на складе
        materials_group = QGroupBox("Склад материалов профилей")
        materials_layout = QVBoxLayout(materials_group)
        
        self.stock_materials_table = QTableWidget()
        setup_table_columns(self.stock_materials_table, [
            'Наименование', 'Длина (мм)', 'Количество шт'
        ])
        enable_table_sorting(self.stock_materials_table, True)
        self.stock_materials_table.setMinimumHeight(150)
        materials_layout.addWidget(self.stock_materials_table)
        
        # Добавляем группы в сплиттер
        splitter.addWidget(remainders_group)
        splitter.addWidget(materials_group)
        splitter.setSizes([150, 150])
        
        layout.addWidget(profiles_group)
        layout.addWidget(splitter)
        
        return main_widget

    def create_fabric_section(self):
        """Создание раздела полотен москитных сеток"""
        main_widget = QWidget()
        layout = QVBoxLayout(main_widget)
        
        # Группа полотен для раскроя
        fabric_group = QGroupBox("Полотна для раскроя")
        fabric_layout = QVBoxLayout(fabric_group)
        
        # Таблица полотен
        self.fabric_table = QTableWidget()
        setup_table_columns(self.fabric_table, [
            'Элемент', 'Артикул полотна', 'Ширина (мм)', 'Высота (мм)', 'Количество'
        ])
        
        # Включаем сортировку
        enable_table_sorting(self.fabric_table, True)
        self.fabric_table.setMinimumHeight(200)
        fabric_layout.addWidget(self.fabric_table)
        
        # Создаем вертикальный сплиттер для двух таблиц складов полотен
        splitter = QSplitter(Qt.Vertical)
        
        # Группа остатков полотен на складе
        fabric_remainders_group = QGroupBox("Склад остатков полотен")
        fabric_remainders_layout = QVBoxLayout(fabric_remainders_group)
        
        self.fabric_remainders_table = QTableWidget()
        setup_table_columns(self.fabric_remainders_table, [
            'Артикул', 'Ширина (мм)', 'Высота (мм)', 'Количество'
        ])
        enable_table_sorting(self.fabric_remainders_table, True)
        self.fabric_remainders_table.setMinimumHeight(150)
        fabric_remainders_layout.addWidget(self.fabric_remainders_table)
        
        # Группа материалов полотен на складе
        fabric_materials_group = QGroupBox("Склад материалов полотен")
        fabric_materials_layout = QVBoxLayout(fabric_materials_group)
        
        self.fabric_materials_table = QTableWidget()
        setup_table_columns(self.fabric_materials_table, [
            'Артикул', 'Ширина (мм)', 'Высота (мм)', 'Количество'
        ])
        enable_table_sorting(self.fabric_materials_table, True)
        self.fabric_materials_table.setMinimumHeight(150)
        fabric_materials_layout.addWidget(self.fabric_materials_table)
        
        # Добавляем группы в сплиттер
        splitter.addWidget(fabric_remainders_group)
        splitter.addWidget(fabric_materials_group)
        splitter.setSizes([150, 150])
        
        layout.addWidget(fabric_group)
        layout.addWidget(splitter)
        
        return main_widget

    def create_stock_groups(self):
        """Создание групп складов (остатки и материалы)"""
        # Основной контейнер
        main_widget = QWidget()
        layout = QVBoxLayout(main_widget)
        
        # Создаем вертикальный сплиттер для двух таблиц складов
        splitter = QSplitter(Qt.Vertical)
        
        # Группа остатков профилей на складе
        remainders_group = QGroupBox("Склад остатков профилей")
        remainders_layout = QVBoxLayout(remainders_group)
        
        self.stock_remainders_table = QTableWidget()
        setup_table_columns(self.stock_remainders_table, [
            'Наименование', 'Длина (мм)', 'Количество палок'
        ])
        enable_table_sorting(self.stock_remainders_table, True)
        self.stock_remainders_table.setMinimumHeight(200)
        remainders_layout.addWidget(self.stock_remainders_table)
        
        # Группа материалов профилей на складе
        materials_group = QGroupBox("Склад материалов профилей")
        materials_layout = QVBoxLayout(materials_group)
        
        self.stock_materials_table = QTableWidget()
        setup_table_columns(self.stock_materials_table, [
            'Наименование', 'Длина (мм)', 'Количество шт'
        ])
        enable_table_sorting(self.stock_materials_table, True)
        self.stock_materials_table.setMinimumHeight(200)
        materials_layout.addWidget(self.stock_materials_table)
        
        # Добавляем группы в сплиттер
        splitter.addWidget(remainders_group)
        splitter.addWidget(materials_group)
        splitter.setSizes([300, 300])
        
        layout.addWidget(splitter)
        
        return main_widget



    def create_results_tab(self):
        """Создание вкладки результатов оптимизации"""
        results_tab = QWidget()
        layout = QVBoxLayout(results_tab)
        
        # Статистика вверху
        stats_group = self.create_statistics_group()
        layout.addWidget(stats_group)
        
        # Таблица результатов
        results_group = QGroupBox("План распила")
        results_layout = QVBoxLayout(results_group)
        
        self.results_table = QTableWidget()
        setup_table_columns(self.results_table, [
            'Артикул', 'Длина хлыста (мм)', 'Количество хлыстов такого распила', 'Количество деталей на хлысте', 'Распил', 'Деловой остаток (мм)', 'Деловой остаток (%)', 'Отход (мм)', 'Отход (%)'
        ])
        
        # Включаем сортировку
        enable_table_sorting(self.results_table, True)
        self.results_table.setMinimumHeight(400)
        results_layout.addWidget(self.results_table)
        
        # Добавляем кнопки копирования таблицы
        copy_buttons_layout = QHBoxLayout()
        copy_buttons_layout.addStretch()
        
        # Кнопка копирования в текстовом формате
        self.copy_table_button = QPushButton("📋 Копировать таблицу")
        self.copy_table_button.setStyleSheet(SPECIAL_BUTTON_STYLES["copy"])
        self.copy_table_button.clicked.connect(self.on_copy_table_clicked)
        self.copy_table_button.setToolTip("Копирует всю таблицу плана распила в буфер обмена в текстовом формате")
        copy_buttons_layout.addWidget(self.copy_table_button)
        
        # Кнопка копирования в формате CSV
        self.copy_csv_button = QPushButton("📊 Копировать как CSV")
        self.copy_csv_button.setStyleSheet(SPECIAL_BUTTON_STYLES["copy_csv"])
        self.copy_csv_button.clicked.connect(self.on_copy_csv_clicked)
        self.copy_csv_button.setToolTip("Копирует всю таблицу плана распила в буфер обмена в формате CSV")
        copy_buttons_layout.addWidget(self.copy_csv_button)
        
        copy_buttons_layout.addStretch()
        results_layout.addLayout(copy_buttons_layout)
        
        results_group.setLayout(results_layout)
        layout.addWidget(results_group)
        
        self.tabs.addTab(results_tab, "📈 Результаты оптимизации")





    def create_visualization_tab(self):
        """Создание вкладки визуализации"""
        print("🔧 DEBUG: Создание вкладки визуализации")
        self.visualization_tab = VisualizationTab()
        self.tabs.addTab(self.visualization_tab, "👁️ Визуализация раскроя")
        print(f"🔧 DEBUG: Вкладка визуализации создана: {self.visualization_tab}")

    def create_statistics_group(self):
        """Создание группы статистики"""
        group = QGroupBox("Общая информация о результатах оптимизации")
        layout = QVBoxLayout(group)
        
        # Основные статистики
        stats_layout = QHBoxLayout()
        
        # Левая колонка - общая информация
        left_layout = QFormLayout()
        
        # Стиль для значений статистики
        stats_style = WIDGET_CONFIGS["stats_labels"]["default"]
        
        self.stats_total_stocks = QLabel("0")
        self.stats_total_stocks.setStyleSheet(stats_style)
        left_layout.addRow("Использовано хлыстов:", self.stats_total_stocks)
        
        self.stats_total_cuts = QLabel("0")
        self.stats_total_cuts.setStyleSheet(stats_style)
        left_layout.addRow("Всего распилов:", self.stats_total_cuts)
        
        self.stats_total_length = QLabel("0 м")
        self.stats_total_length.setStyleSheet(stats_style)
        left_layout.addRow("Общая длина:", self.stats_total_length)
        
        # Новая строка: распределено деталей
        self.stats_distributed_pieces = QLabel("0/0")
        self.stats_distributed_pieces.setStyleSheet(stats_style)
        left_layout.addRow("Распределено деталей:", self.stats_distributed_pieces)
        
        stats_layout.addLayout(left_layout)
        
        # Правая часть - эффективность
        right_layout = QFormLayout()
        
        # Стиль для отходов (красный)
        waste_style = WIDGET_CONFIGS["stats_labels"]["waste"]
        
        self.stats_waste_length = QLabel("0 м")
        self.stats_waste_length.setStyleSheet(waste_style)
        right_layout.addRow("Отходы:", self.stats_waste_length)
        
        self.stats_waste_percent = QLabel("0.00 %")
        self.stats_waste_percent.setStyleSheet(waste_style)
        right_layout.addRow("Процент отходов:", self.stats_waste_percent)
        
        self.stats_efficiency = QLabel("0.00 %")
        self.stats_efficiency.setStyleSheet(WIDGET_CONFIGS["stats_labels"]["remnants"])
        right_layout.addRow("Эффективность:", self.stats_efficiency)
        
        # Добавляем статистику деловых остатков
        self.stats_remainders_length = QLabel("0 м")
        self.stats_remainders_length.setStyleSheet(WIDGET_CONFIGS["stats_labels"]["remnants"])
        right_layout.addRow("Деловые остатки:", self.stats_remainders_length)
        
        self.stats_remainders_percent = QLabel("0.00 %")
        self.stats_remainders_percent.setStyleSheet(WIDGET_CONFIGS["stats_labels"]["remnants"])
        right_layout.addRow("Процент остатков:", self.stats_remainders_percent)
        
        stats_layout.addLayout(right_layout)
        layout.addLayout(stats_layout)
        
        # Кнопка загрузки данных в Altawin (MOS)
        upload_layout = QHBoxLayout()
        upload_layout.addStretch()
        
        # Галочка для корректировки материалов в Altawin
        self.adjust_materials_checkbox = QCheckBox("Скорректировать списание материалов в Altawin")
        self.adjust_materials_checkbox.setChecked(True)
        self.adjust_materials_checkbox.setStyleSheet("QCheckBox { color: #e0e0e0; font-weight: bold; }")
        upload_layout.addWidget(self.adjust_materials_checkbox)
        
        # Кнопка загрузки данных в Altawin (MOS)
        self.upload_mos_to_altawin_button = QPushButton("📤 Загрузить данные в Altawin (MOS)")
        self.upload_mos_to_altawin_button.setStyleSheet(SPECIAL_BUTTON_STYLES["upload"])
        self.upload_mos_to_altawin_button.clicked.connect(self.on_upload_mos_clicked)
        self.upload_mos_to_altawin_button.setEnabled(False)
        upload_layout.addWidget(self.upload_mos_to_altawin_button)
        
        upload_layout.addStretch()
        
        layout.addLayout(upload_layout)
        
        return group

    # ========== МЕТОДЫ ЗАГРУЗКИ ДАННЫХ ==========
    
    def on_load_data_clicked(self):
        """Обработчик загрузки данных с API"""
        order_ids_text = self.order_id_input.text().strip()
        if not order_ids_text:
            QMessageBox.warning(self, "Ошибка", "Введите grorders_mos_id")
            return

        # Получаем список grorderid по введенному grorders_mos_id через API
        try:
            mos_id = int(order_ids_text)
        except ValueError:
            QMessageBox.warning(self, "Ошибка", "grorders_mos_id должен быть целым числом")
            return

        try:
            grorder_ids = self.api_client.get_grorders_by_mos_id(mos_id)
            if not grorder_ids:
                QMessageBox.warning(self, "Данные не найдены", "По указанному grorders_mos_id не найдено связанных grorderid")
                return
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось получить grorderid: {str(e)}")
            return
        
        # Блокируем кнопку
        self.load_data_button.setEnabled(False)
        self.load_data_button.setText("Загрузка...")
        
        # Открываем диалог отладки
        self.debug_dialog = DebugDialog(self)
        self.debug_dialog.show()
        
        # Останавливаем предыдущий поток если он еще работает
        if self.data_load_thread and self.data_load_thread.isRunning():
            self.data_load_thread.terminate()
            self.data_load_thread.wait()
        
        # Создаем и настраиваем новый поток загрузки
        self.data_load_thread = DataLoadThread(self.api_client, grorder_ids, mos_id)
        
        # Подключаем сигналы потока к методам главного окна
        self.data_load_thread.debug_step.connect(self._add_debug_step_safe)
        self.data_load_thread.error_occurred.connect(self._show_error_safe)
        self.data_load_thread.success_occurred.connect(self._show_success_safe)
        self.data_load_thread.data_loaded.connect(self._update_tables_safe)
        self.data_load_thread.finished_loading.connect(self._restore_button_safe)
        
        # Запускаем поток
        self.data_load_thread.start()

    # ========== МЕТОДЫ ОПТИМИЗАЦИИ ==========
    
    def on_optimize_clicked(self):
        """Обработчик кнопки оптимизации"""
        print("🔧 DEBUG: === НАЧАЛО ОПТИМИЗАЦИИ ===")
        print(f"🔧 DEBUG: self.profiles: {len(self.profiles) if self.profiles else 0} элементов")
        print(f"🔧 DEBUG: self.fabric_details: {len(self.fabric_details) if self.fabric_details else 0} элементов")

        # Проверяем данные
        if not self.profiles:
            QMessageBox.warning(self, "Предупреждение", "Сначала загрузите данные заказа")
            return
            
        if not hasattr(self, 'stocks') or not self.stocks:
            QMessageBox.warning(self, "Предупреждение", "Нет данных о хлыстах на складе")
            return
        
        print(f"🔧 DEBUG: Запуск оптимизации с {len(self.profiles)} профилями и {len(self.stocks)} хлыстами (до фильтра)")
        
        # Блокируем кнопку
        self.optimize_button.setEnabled(False)
        self.optimize_button.setText("Оптимизация...")
        
        # Очищаем вкладку визуализации перед запуском новой оптимизации
        if hasattr(self, 'visualization_tab'):
            self.visualization_tab.clear_visualization()

        # Показываем диалог прогресса
        self.progress_dialog = ProgressDialog(self)
        self.progress_dialog.show()
        
        # Собираем параметры оптимизации
        # Обновляем настройки из сохраненных параметров
        self.current_settings.blade_width = self.optimization_params['blade_width']
        self.current_settings.min_remainder_length = self.optimization_params['min_remainder_length']
        self.current_settings.min_trash_mm = self.optimization_params['min_trash_mm']
        self.current_settings.begin_indent = self.optimization_params['begin_indent']
        self.current_settings.end_indent = self.optimization_params['end_indent']
        self.current_settings.max_waste_percent = self.optimization_params['max_waste_percent']
        self.current_settings.pair_optimization = self.optimization_params['pair_optimization']
        self.current_settings.use_remainders = self.optimization_params['use_remainders']
        # Новые параметры парной оптимизации
        self.current_settings.pairing_exact_bonus = self.optimization_params['pairing_exact_bonus']
        self.current_settings.pairing_partial_bonus = self.optimization_params['pairing_partial_bonus']
        self.current_settings.pairing_partial_threshold = self.optimization_params['pairing_partial_threshold']
        self.current_settings.pairing_new_simple_bonus = self.optimization_params['pairing_new_simple_bonus']
        
        # Формируем список хлыстов согласно настройке использования остатков
        stocks_for_optimization = self.stocks
        try:
            if not self.current_settings.use_remainders:
                stocks_for_optimization = [s for s in self.stocks if not bool(getattr(s, 'is_remainder', False))]
        except Exception:
            stocks_for_optimization = self.stocks
        print(f"🔧 DEBUG: К оптимизации передано {len(stocks_for_optimization)} хлыстов (use_remainders={self.current_settings.use_remainders})")

        # Останавливаем предыдущий поток если он еще работает
        if self.optimization_thread and self.optimization_thread.isRunning():
            self.optimization_thread.terminate()
            self.optimization_thread.wait()
        
        # Создаем и настраиваем новый поток оптимизации
        self.optimization_thread = OptimizationThread(
            self.optimizer, 
            self.profiles, 
            stocks_for_optimization, 
            self.current_settings
        )
        
        # Подключаем сигналы потока к методам главного окна
        self.optimization_thread.debug_step.connect(self._add_debug_step_safe)
        self.optimization_thread.optimization_result.connect(self._handle_optimization_result)
        self.optimization_thread.optimization_error.connect(self._handle_optimization_error)
        self.optimization_thread.progress_updated.connect(self._update_progress)
        self.optimization_thread.finished_optimization.connect(self._close_progress_dialog)
        
        # Запускаем поток оптимизации профилей
        self.optimization_thread.start()

        # Запускаем оптимизацию фибергласса если есть данные
        print(f"🔧 DEBUG: Проверка fabric_details: {self.fabric_details}")
        if self.fabric_details:
            print(f"🔧 DEBUG: Запуск оптимизации фибергласса с {len(self.fabric_details)} деталями")
            self._run_fiberglass_optimization()
        else:
            print("🔧 DEBUG: fabric_details пустой, оптимизация фибергласса не запускается")

    def _run_fiberglass_optimization(self):
        """Запуск оптимизации фибергласса"""
        print("🔧 DEBUG: === НАЧАЛО ОПТИМИЗАЦИИ ФИБЕРГЛАССА ===")
        print(f"🔧 DEBUG: self.fabric_details: {self.fabric_details}")
        print(f"🔧 DEBUG: len(self.fabric_details): {len(self.fabric_details) if self.fabric_details else 'N/A'}")
        print(f"🔧 DEBUG: self.fabric_materials: {self.fabric_materials}")
        print(f"🔧 DEBUG: self.fabric_remainders: {self.fabric_remainders}")

        try:
            # Подготавливаем данные для оптимизации фибергласса
            print("🔧 DEBUG: Преобразование FiberglassDetail в словари")

            # Преобразуем FiberglassDetail объекты в словари
            details_dict = []
            for detail in self.fabric_details:
                detail_dict = {
                    'orderitemsid': str(detail.orderitemsid),
                    'width': detail.width,
                    'height': detail.height,
                    'g_marking': detail.marking,
                    'total_qty': detail.quantity,
                    'goodsid': detail.goodsid,
                    'gp_marking': detail.marking,
                    'oi_name': detail.item_name,
                    'orderno': detail.orderno,  # Номер заказа
                    'item_name': detail.item_name,  # Номер изделия
                    'izdpart': detail.izdpart  # Номер части изделия
                }
                details_dict.append(detail_dict)

            # Преобразуем FiberglassSheet объекты в словари
            materials_dict = []
            for material in self.fabric_materials:
                material_dict = {
                    'id': str(material.goodsid),  # Используем goodsid как ID
                    'width': material.width,
                    'height': material.height,
                    'g_marking': material.marking,
                    'cost': 1500.0,  # Заглушка для стоимости
                    'goodsid': material.goodsid,
                    'quantity': material.quantity
                }
                materials_dict.append(material_dict)

            remainders_dict = []
            for remainder in self.fabric_remainders:
                remainder_dict = {
                    'id': str(remainder.remainder_id if remainder.remainder_id else remainder.goodsid),
                    'width': remainder.width,
                    'height': remainder.height,
                    'g_marking': remainder.marking,
                    'cost': 800.0,  # Заглушка для стоимости
                    'goodsid': remainder.goodsid,
                    'quantity': remainder.quantity
                }
                remainders_dict.append(remainder_dict)

            fabric_params = {
                'planar_min_remainder_width': self.optimization_params.get('planar_min_remainder_width', 500.0),
                'planar_min_remainder_height': self.optimization_params.get('planar_min_remainder_height', 500.0),
                'planar_cut_width': self.optimization_params.get('planar_cut_width', 1.0),
                'sheet_indent': self.optimization_params.get('sheet_indent', 15.0),
                'remainder_indent': self.optimization_params.get('remainder_indent', 15.0),
                'planar_max_waste_percent': self.optimization_params.get('planar_max_waste_percent', 5.0),
                'use_warehouse_remnants': self.optimization_params.get('use_warehouse_remnants', True),
                'allow_rotation': self.optimization_params.get('allow_rotation', True)
            }

            # Запускаем оптимизацию фибергласса
            def progress_callback(percent):
                """Коллбэк для прогресса оптимизации фибергласса"""
                self._add_debug_step_safe(f"Фибергласс: {percent:.1f}%")

            self.debug_step_signal.emit("🪟 Запуск оптимизации фибергласса...")

            print("🔧 DEBUG: Вызываем optimize_fiberglass с параметрами:")
            print(f"  - details: {len(details_dict)} элементов")
            print(f"  - materials: {len(materials_dict)} элементов")
            print(f"  - remainders: {len(remainders_dict)} элементов")
            print(f"  - params: {fabric_params}")

            # Генерируем единую карту ячеек ПЕРЕД вызовом оптимизации
            cell_map = self._generate_cell_map()
            if not cell_map:
                self.debug_step_signal.emit("⚠️ Не удалось сгенерировать карту ячеек для фибергласса.")

            # Синхронный вызов общего адаптера данных и неизменённого
            # алгоритма фибергласса.
            self.fabric_optimization_result = optimize_fiberglass_collections(
                self.fabric_details,
                self.fabric_remainders,
                self.fabric_materials,
                fabric_params,
                cell_map,
                progress_callback,
            )

            print(f"🔧 DEBUG: optimize_fiberglass вернул: {self.fabric_optimization_result}")
            print(f"🔧 DEBUG: Тип результата: {type(self.fabric_optimization_result)}")
            if self.fabric_optimization_result:
                print(f"🔧 DEBUG: Результат success: {getattr(self.fabric_optimization_result, 'success', 'NO ATTR')}")
                print(f"🔧 DEBUG: Результат layouts: {getattr(self.fabric_optimization_result, 'layouts', 'NO ATTR')}")
                if hasattr(self.fabric_optimization_result, 'layouts') and self.fabric_optimization_result.layouts:
                    print(f"🔧 DEBUG: Количество layouts: {len(self.fabric_optimization_result.layouts)}")

            if self.fabric_optimization_result and self.fabric_optimization_result.success:
                self.debug_step_signal.emit("✅ Оптимизация фибергласса завершена успешно")

                # Дополнительная отладка результатов
                if hasattr(self.fabric_optimization_result, 'layouts') and self.fabric_optimization_result.layouts:
                    total_remnants = sum(len(layout.get_remnants()) for layout in self.fabric_optimization_result.layouts)
                    total_waste = sum(len(layout.get_waste()) for layout in self.fabric_optimization_result.layouts)
                    total_details = sum(len(layout.get_placed_details()) for layout in self.fabric_optimization_result.layouts)
                    print(f"🔧 DEBUG: Детали: {total_details}, Остатки: {total_remnants}, Отходы: {total_waste}")

                    # Проверяем каждый layout на наличие деловых остатков
                    for i, layout in enumerate(self.fabric_optimization_result.layouts):
                        remnants = layout.get_remnants()
                        if remnants:
                            print(f"🔧 DEBUG: Layout {i+1} содержит {len(remnants)} деловых остатков:")
                            for remnant in remnants:
                                print(f"    - Остаток: {remnant.width:.0f}x{remnant.height:.0f}мм, тип: {remnant.item_type}")

                # Испускаем сигнал для обновления визуализации
                self.debug_step_signal.emit(f"🔄 Испускаем сигнал обновления визуализации с {len(self.fabric_optimization_result.layouts) if self.fabric_optimization_result.layouts else 0} рулонами")
                self.update_visualization_signal.emit(self.fabric_optimization_result)
            else:
                error_msg = "Оптимизация фибергласса не удалась"
                if self.fabric_optimization_result and hasattr(self.fabric_optimization_result, 'message'):
                    error_msg = self.fabric_optimization_result.message
                self.debug_step_signal.emit(f"❌ {error_msg}")
                
                # Проверяем, является ли это критической ошибкой нехватки материалов
                if "КРИТИЧЕСКАЯ ОШИБКА: НЕХВАТКА ФИБЕРГЛАССА" in error_msg:
                    # КРИТИЧЕСКАЯ ОШИБКА - показываем красное окно с ошибкой
                    QMessageBox.critical(
                        self,
                        "❌ Критическая ошибка: Нехватка фибергласса",
                        error_msg
                    )
                elif "НЕХВАТКА" in error_msg or "не хватает" in error_msg.lower():
                    # Обычное предупреждение о нехватке материалов
                    QMessageBox.warning(
                        self,
                        "⚠️ Нехватка материалов",
                        error_msg
                    )
                else:
                    # Другие ошибки
                    QMessageBox.warning(
                        self,
                        "⚠️ Ошибка оптимизации фибергласса",
                        error_msg
                    )
                
                # Даже при неудаче передаем результат для отображения информации об ошибке
                self.update_visualization_signal.emit(self.fabric_optimization_result)

        except Exception as e:
            self.debug_step_signal.emit(f"❌ Ошибка оптимизации фибергласса: {str(e)}")
            import traceback
            print(f"Ошибка оптимизации фибергласса: {traceback.format_exc()}")

    def _update_visualization_tab(self, result):
        """Thread-safe обновление вкладки визуализации"""
        try:
            self.debug_step_signal.emit("🔧 _update_visualization_tab вызван")
            if hasattr(self, 'visualization_tab') and self.visualization_tab is not None:
                self.debug_step_signal.emit("✅ visualization_tab найден, вызываем set_optimization_result")
                # Используем QTimer для отложенного вызова, чтобы интерфейс был полностью готов
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(100, lambda: self._safe_set_visualization_result(result))
            else:
                self.debug_step_signal.emit("❌ visualization_tab не найден!")
                print(f"Available attributes: {[attr for attr in dir(self) if 'visual' in attr.lower()]}")
        except Exception as e:
            self.debug_step_signal.emit(f"❌ Ошибка обновления визуализации: {str(e)}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")

    def _safe_set_visualization_result(self, result):
        """Безопасная установка результата визуализации с задержкой"""
        try:
            if hasattr(self, 'visualization_tab') and self.visualization_tab is not None:
                self.visualization_tab.set_optimization_result(result)
                if result and hasattr(result, 'layouts') and result.layouts:
                    self.debug_step_signal.emit(f"✅ Вкладка визуализации обновлена: {len(result.layouts)} рулонов")
                else:
                    self.debug_step_signal.emit("ℹ️ Вкладка визуализации очищена (нет данных)")
            else:
                self.debug_step_signal.emit("❌ visualization_tab не доступен при отложенном вызове")
        except Exception as e:
            self.debug_step_signal.emit(f"❌ Ошибка в _safe_set_visualization_result: {str(e)}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")

    def on_save_settings_clicked(self):
        """Сохранение текущих параметров оптимизации"""
        # Здесь можно реализовать сохранение настроек в файл
        settings = {
            'blade_width': self.blade_width.value(),
            'min_remainder_length': self.min_remainder_length.value(),
            'max_waste_percent': self.max_waste_percent.value(),
            'pair_optimization': self.pair_optimization.isChecked(),
            'use_remainders': self.use_remainders.isChecked(),
            # Новые параметры парной оптимизации (если есть элементы UI — пока берем из current_settings)
            'pairing_exact_bonus': getattr(self.current_settings, 'pairing_exact_bonus', 3000.0),
            'pairing_partial_bonus': getattr(self.current_settings, 'pairing_partial_bonus', 1000.0),
            'pairing_partial_threshold': getattr(self.current_settings, 'pairing_partial_threshold', 0.7),
            'pairing_new_simple_bonus': getattr(self.current_settings, 'pairing_new_simple_bonus', 150.0)
        }
        
        # TODO: Сохранить в файл настроек
        QMessageBox.information(self, "Настройки", "Параметры оптимизации сохранены")

    # ========== ОБРАБОТЧИКИ СИГНАЛОВ ==========
    
    def _add_debug_step(self, message):
        """Добавление шага отладки"""
        print(f"🔧 DEBUG: {message}")
        self.debug_step_signal.emit(message)
    
    def _add_debug_step_safe(self, message):
        """Thread-safe добавление шага отладки"""
        if self.debug_dialog:
            self.debug_dialog.add_step(message)
    
    def _show_error_safe(self, title, message, icon):
        """Thread-safe показ ошибки"""
        print(f"❌ {title}: {message}")
        QMessageBox.critical(self, title, message)
    
    def _show_success_safe(self):
        """Thread-safe показ успеха"""
        if self.debug_dialog:
            QTimer.singleShot(2000, self.debug_dialog.close)
    
    def _update_tables_safe(self, profiles, stock_data, fabric_details, fabric_stock_data):
        """Thread-safe обновление таблиц"""
        try:
            # Сохраняем данные
            self.profiles = profiles
            self.stock_remainders = stock_data.get('remainders', [])
            self.stock_materials = stock_data.get('materials', [])

            # Сохраняем данные полотен
            print(f"🔧 DEBUG: Присваиваем fabric_details. Было: {len(getattr(self, 'fabric_details', []))} элементов")
            self.fabric_details = fabric_details  # КРИТИЧНО: присваиваем self.fabric_details!
            self.current_fabric_details = fabric_details
            print(f"🔧 DEBUG: После присваивания: {len(self.fabric_details)} элементов в self.fabric_details")
            print(f"🔧 DEBUG: self.fabric_details is None: {self.fabric_details is None}")
            if self.fabric_details:
                print(f"🔧 DEBUG: Тип self.fabric_details: {type(self.fabric_details)}")
            self.fabric_remainders = fabric_stock_data.get('remainders', [])
            self.fabric_materials = fabric_stock_data.get('materials', [])
            self.current_fabric_remainders = fabric_stock_data.get('remainders', [])
            self.current_fabric_materials = fabric_stock_data.get('materials', [])




            
            # Парсим ID заказов для отображения
            order_ids_text = self.order_id_input.text().strip()
            order_ids = []
            if order_ids_text:
                for order_id_str in order_ids_text.split(','):
                    order_id = order_id_str.strip()
                    if order_id and order_id.isdigit():
                        order_ids.append(int(order_id))
            
            # Общая подготовка stock-объектов: каждый складской остаток
            # остаётся отдельной физической палкой, как и раньше.
            self.stocks = build_stocks(self.stock_remainders, self.stock_materials)
            
            print(f"🔧 DEBUG: Создано {len(self.stocks)} хлыстов для оптимизации")
            
            # Обновляем таблицы профилей
            fill_profiles_table(self.profiles_table, [p.__dict__ for p in profiles])
            fill_stock_remainders_table(self.stock_remainders_table, [r.__dict__ for r in self.stock_remainders])
            fill_stock_materials_table(self.stock_materials_table, [m.__dict__ for m in self.stock_materials])

            # Обновляем таблицы полотен
            # Для полотен пока используем тот же формат, что и для профилей, но с другими колонками
            fill_fabric_details_table(self.fabric_table, [f.__dict__ for f in fabric_details])
            fill_fabric_remainders_table(self.fabric_remainders_table, [r.__dict__ for r in self.fabric_remainders])
            fill_fabric_materials_table(self.fabric_materials_table, [m.__dict__ for m in self.fabric_materials])
            
            # Обновляем информацию о заказах
            total_stock_items = len(self.stock_remainders) + len(self.stock_materials)
            total_fabric_stock_items = len(self.fabric_remainders) + len(self.fabric_materials)
            if len(order_ids) == 1:
                order_info = f"Заказ {order_ids[0]}: {len(profiles)} профилей, {len(fabric_details)} полотен, {total_stock_items} материалов профилей, {total_fabric_stock_items} материалов полотен"
            else:
                order_info = f"Заказы {', '.join(map(str, order_ids))}: {len(profiles)} профилей, {len(fabric_details)} полотен, {total_stock_items} материалов профилей, {total_fabric_stock_items} материалов полотен"
            
            self.order_info_label.setText(order_info)
            
            # Активируем кнопку оптимизации
            self.optimize_button.setEnabled(True)
            
            # Автоматически подгоняем ширину столбцов
            QTimer.singleShot(500, lambda: [
                update_table_column_widths(self.profiles_table),
                update_table_column_widths(self.stock_remainders_table),
                update_table_column_widths(self.stock_materials_table),
                update_table_column_widths(self.fabric_table),
                update_table_column_widths(self.fabric_remainders_table),
                update_table_column_widths(self.fabric_materials_table)
            ])
            
        except Exception as e:
            print(f"❌ Ошибка обновления таблиц: {e}")
    
    def _restore_button_safe(self):
        """Thread-safe восстановление кнопки"""
        self.load_data_button.setEnabled(True)
        self.load_data_button.setText("Загрузить данные")
    
    def _handle_optimization_result(self, result):
        """Обработка результата оптимизации"""
        try:
            self.optimization_result = result
            
            # Восстанавливаем кнопку
            self.optimize_button.setEnabled(True)
            self.optimize_button.setText("🚀 Запустить оптимизацию")
            
            # Обновляем статистику
            self._update_statistics(result)
            
            # Обновляем таблицу результатов
            if result.cut_plans:
                fill_optimization_results_table(self.results_table, result.cut_plans)
            else:
                print("⚠️ Нет планов распила для отображения")
            
                        # Активируем кнопку загрузки в Altawin (MOS)
            self.upload_mos_to_altawin_button.setEnabled(True)

            # Обновляем вкладку визуализации с результатами фибергласса (если они есть)
            if hasattr(self, 'fabric_optimization_result') and self.fabric_optimization_result:
                self.update_visualization_signal.emit(self.fabric_optimization_result)
            else:
                # Если результатов фибергласса нет, передаем пустой результат для очистки вкладки
                self.update_visualization_signal.emit(None)

            # Переключаемся на вкладку результатов
            self.tabs.setCurrentIndex(1)
            
            cut_plans_count = len(result.cut_plans) if result.cut_plans else 0
            print(f"✅ Оптимизация завершена! Использовано хлыстов: {cut_plans_count}")
            
            # НОВОЕ: Проверяем предупреждения о нехватке материалов или повторном использовании остатков
            if result.message:
                if "КРИТИЧЕСКАЯ ОШИБКА: НЕХВАТКА МАТЕРИАЛОВ" in result.message:
                    # КРИТИЧЕСКАЯ ОШИБКА - показываем красное окно с ошибкой
                    QMessageBox.critical(
                        self,
                        "❌ Критическая ошибка: Нехватка материалов",
                        result.message
                    )
                elif "НЕХВАТКА МАТЕРИАЛОВ" in result.message:
                    # Обычное предупреждение о нехватке материалов
                    QMessageBox.warning(
                        self,
                        "⚠️ Нехватка материалов на складе",
                        result.message
                    )
                elif "дублирующиеся деловые остатки" in result.message:
                    QMessageBox.critical(
                        self,
                        "Ошибка данных склада",
                        f"Обнаружены проблемы с деловыми остатками:\n\n{result.message}\n\n"
                        f"Рекомендации:\n"
                        f"• Проверьте данные склада на дублирование остатков\n"
                        f"• Убедитесь, что каждый деловой остаток имеет уникальный warehouseremaindersid\n"
                        f"• Обратитесь к администратору системы"
                    )
            
        except Exception as e:
            print(f"⚠️ Ошибка при обработке результата оптимизации: {e}")
            import traceback
            traceback.print_exc()
            self._handle_optimization_error(f"Ошибка отображения результатов: {str(e)}")
    
    def _handle_optimization_error(self, error_msg):
        """Обработка ошибки оптимизации"""
        # Восстанавливаем кнопку
        self.optimize_button.setEnabled(True)
        self.optimize_button.setText("🚀 Запустить оптимизацию")
        
        # Показываем ошибку
        print(f"❌ Ошибка оптимизации: {error_msg}")
        QMessageBox.critical(self, "Ошибка оптимизации", f"Произошла ошибка во время выполнения оптимизации:\n\n{error_msg}")
    
    def _update_progress(self, percent):
        """Обновление прогресса оптимизации"""
        if self.progress_dialog:
            self.progress_dialog.set_progress(percent)
    
    def _close_progress_dialog(self):
        """Закрытие диалога прогресса"""
        try:
            if self.progress_dialog:
                self.progress_dialog.force_close()
                self.progress_dialog = None
        except Exception as e:
            print(f"⚠️ Ошибка закрытия диалога прогресса: {e}")
    
    def _update_statistics(self, result):
        """Обновление статистики"""
        try:
            stats = result.get_statistics()
            
            # Рассчитываем деловые остатки
            total_remainders = 0
            total_length = stats.get('total_length', 0)
            
            for plan in result.cut_plans:
                remainder = getattr(plan, 'remainder', None)
                if remainder and remainder > 0:
                    total_remainders += remainder
            
            remainders_percent = (total_remainders / total_length * 100) if total_length > 0 else 0
            
            self.stats_total_stocks.setText(str(stats.get('total_stocks', 0)))
            self.stats_total_cuts.setText(str(stats.get('total_cuts', 0)))
            self.stats_total_length.setText(f"{stats.get('total_length', 0) / 1000:.1f} м")
            self.stats_waste_length.setText(f"{stats.get('total_waste', 0) / 1000:.1f} м")
            self.stats_waste_percent.setText(f"{stats.get('waste_percent', 0):.2f} %")
            self.stats_efficiency.setText(f"{100 - stats.get('waste_percent', 0):.2f} %")
            
            # Обновляем статистику деловых остатков
            self.stats_remainders_length.setText(f"{total_remainders / 1000:.1f} м")
            self.stats_remainders_percent.setText(f"{remainders_percent:.2f} %")

            # Обновляем строку "Распределено деталей"
            # Используем только данные из статистики результата оптимизации
            total_pieces_needed = int(stats.get('total_pieces_needed', 0))
            total_pieces_placed = int(stats.get('total_pieces_placed', 0))
            
                        # Если статистика из оптимизатора отсутствует, считаем заново
            if total_pieces_needed == 0 and self.profiles:
                try:
                    total_pieces_needed = sum(int(getattr(p, 'quantity', 0)) for p in self.profiles)
                except Exception as e:
                    print(f"⚠️ Ошибка подсчета needed pieces: {e}")
                    total_pieces_needed = 0

            if total_pieces_placed == 0 and getattr(result, 'cut_plans', None):
                try:
                    total_pieces_placed = 0
                    for plan in result.cut_plans:
                        plan_count = int(getattr(plan, 'count', 1))
                        plan_pieces = plan.get_cuts_count()
                        total_pieces_placed += plan_pieces * plan_count
                except Exception as e:
                    print(f"⚠️ Ошибка подсчета placed pieces: {e}")
                    total_pieces_placed = 0

            self.stats_distributed_pieces.setText(f"{total_pieces_placed}/{total_pieces_needed}")
        except Exception as e:
            print(f"⚠️ Ошибка при обновлении статистики: {e}")
            # Устанавливаем значения по умолчанию
            self.stats_total_stocks.setText("0")
            self.stats_total_cuts.setText("0")
            self.stats_total_length.setText("0.0 м")
            self.stats_waste_length.setText("0.0 м")
            self.stats_waste_percent.setText("0.00 %")
            self.stats_efficiency.setText("100.00 %")
            self.stats_remainders_length.setText("0.0 м")
            self.stats_remainders_percent.setText("0.00 %")
            self.stats_distributed_pieces.setText("0/0")

    # ========== МЕТОДЫ МЕНЮ ==========
    
    def new_optimization(self):
        """Начать новую оптимизацию"""
        self.order_id_input.clear()
        clear_table(self.profiles_table)
        clear_table(self.stock_remainders_table)
        clear_table(self.stock_materials_table)
        clear_table(self.fabric_table)
        clear_table(self.fabric_remainders_table)
        clear_table(self.fabric_materials_table)
        clear_table(self.results_table)
        self.optimization_result = None

        self.upload_mos_to_altawin_button.setEnabled(False)
        self.optimize_button.setEnabled(False)
        self.order_info_label.setText("<заказ не загружен>")



        self.status_bar.showMessage("Готов к работе")
        self.tabs.setCurrentIndex(0)

        # Сбрасываем галочку корректировки материалов
        self.adjust_materials_checkbox.setChecked(True)

    def on_upload_mos_clicked(self):
        """Загрузка данных оптимизации в OPTIMIZED_MOS/OPTDETAIL_MOS"""
        if not self.optimization_result:
            QMessageBox.warning(self, "Предупреждение", "Нет результатов для сохранения")
            return

        order_ids_text = self.order_id_input.text().strip()
        try:
            grorders_mos_id = int(order_ids_text)
        except ValueError:
            QMessageBox.warning(self, "Ошибка", "grorders_mos_id должен быть целым числом")
            return

        # Проверяем, нужно ли корректировать материалы в Altawin
        adjust_materials = self.adjust_materials_checkbox.isChecked()
        
        # Формируем сообщение для подтверждения
        confirm_message = (
            "Вы точно хотите загрузить данные оптимизации в таблицы MOS?\n\n"
            f"GRORDERS_MOS_ID: {grorders_mos_id}\n"
            f"Планов распила: {len(self.optimization_result.cut_plans)}"
        )
        
        if adjust_materials:
            confirm_message += "\n\n⚠️ ВНИМАНИЕ: После загрузки результатов будет выполнена корректировка списания и прихода материалов в Altawin!"
            confirm_message += "\nЭто приведет к удалению старых данных и созданию новых документов."

        reply = QMessageBox.question(
            self,
            "Подтверждение загрузки (MOS)",
            confirm_message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        try:
            self.status_bar.showMessage("Загрузка результатов оптимизации в таблицы MOS...")
            self.upload_mos_to_altawin_button.setEnabled(False)

            # ШАГ 1: Сначала загружаем результаты оптимизации в таблицы OPTIMIZED_MOS и OPTDETAIL_MOS
            self.status_bar.showMessage("Загрузка результатов оптимизации в таблицы MOS...")
            
            # Используем текущие параметры распила из сохраненных настроек
            blade_width = int(self.optimization_params.get('blade_width', 5))
            min_remainder = int(self.optimization_params.get('min_remainder_length', 300))

            # Загружаем результаты оптимизации
            upload_success = self.api_client.upload_mos_data(
                grorders_mos_id=grorders_mos_id,
                result=self.optimization_result,
                profiles=self.profiles,
                blade_width_mm=blade_width,
                min_remainder_mm=min_remainder,
                begin_indent_mm=int(self.optimization_params.get('begin_indent', 10)),
                end_indent_mm=int(self.optimization_params.get('end_indent', 10)),
                min_trash_mm=int(self.optimization_params.get('min_trash_mm', 50)),
            )

            if not upload_success:
                QMessageBox.critical(self, "Ошибка", "Не удалось загрузить результаты оптимизации в таблицы MOS")
                self.status_bar.showMessage("Ошибка загрузки результатов оптимизации")
                return

            self.status_bar.showMessage("Результаты оптимизации успешно загружены. Корректировка материалов...")
            
            # ШАГ 2: Корректируем материалы (если включено)
            if adjust_materials:
                try:
                    self.status_bar.showMessage("Корректировка материалов в Altawin...")
                    
                    # Формируем данные об использованных материалах и деловых остатках
                    used_materials = []
                    business_remainders = []
                    
                    # Анализируем результаты оптимизации
                    print(f"🔧 DEBUG: Анализируем {len(self.optimization_result.cut_plans)} планов оптимизации...")
                    print("🔧 DEBUG: Проверяем атрибут count для каждого плана:")
                    for i, plan in enumerate(self.optimization_result.cut_plans):
                        count = getattr(plan, 'count', 1)
                        print(f"   План {i+1}: count={count}")
                    
                    # Сначала группируем планы по размеру и типу для правильного подсчета количества
                    # Ключ: (goodsid, length, is_remainder) - убираем warehouseremaindersid из ключа
                    materials_by_size = {}  # Ключ: (goodsid, length, is_remainder)
                    
                    for plan_index, plan in enumerate(self.optimization_result.cut_plans):
                        # Получаем информацию о хлысте
                        stock_length = getattr(plan, 'stock_length', 0)
                        is_remainder = getattr(plan, 'is_remainder', False)
                        warehouseremaindersid = getattr(plan, 'warehouseremaindersid', None)
                        plan_count = getattr(plan, 'count', 1)  # Количество хлыстов в плане
                        
                        # Определяем goodsid (используем profile_id из первого распила)
                        goodsid = None
                        if plan.cuts and len(plan.cuts) > 0:
                            goodsid = plan.cuts[0].get('profile_id')
                        
                        print(f"🔧 DEBUG: План {plan_index + 1}: goodsid={goodsid}, length={stock_length}, is_remainder={is_remainder}, warehouseremaindersid={warehouseremaindersid}, count={plan_count}")
                        
                        if goodsid:
                            # Создаем ключ для группировки БЕЗ warehouseremaindersid
                            # Это позволит группировать все хлысты одного размера и типа
                            material_key = (goodsid, stock_length, is_remainder)
                            
                            if material_key not in materials_by_size:
                                materials_by_size[material_key] = {
                                    'goodsid': goodsid,
                                    'length': stock_length,
                                    'quantity': 0,  # Будем накапливать количество
                                    'is_remainder': is_remainder,
                                    'warehouseremaindersid': warehouseremaindersid  # Сохраняем для отладки
                                }
                            
                            # Увеличиваем количество для этого размера на количество хлыстов в плане
                            materials_by_size[material_key]['quantity'] += plan_count
                            print(f"🔧 DEBUG: Увеличено количество для ключа {material_key}: теперь {materials_by_size[material_key]['quantity']}шт (добавлено {plan_count}шт)")
                    
                    # Теперь формируем used_materials с правильным количеством
                    print("🔧 DEBUG: Итоговая группировка материалов:")
                    for key, data in materials_by_size.items():
                        print(f"   Ключ {key}: goodsid={data['goodsid']}, length={data['length']}, quantity={data['quantity']}шт, is_remainder={data['is_remainder']}")
                    
                    used_materials = []
                    for material_data in materials_by_size.values():
                        # Получаем groupgoods_thick для этого профиля
                        profile_code = None
                        for profile in self.profiles:
                            if profile.id == material_data['goodsid']:
                                profile_code = profile.profile_code
                                break
                        
                        groupgoods_thick = 6000  # По умолчанию 6000 мм
                        if profile_code:
                            for profile in self.profiles:
                                if profile.profile_code == profile_code:
                                    groupgoods_thick = getattr(profile, 'groupgoods_thick', 6000)
                                    break
                        
                        # Добавляем атрибуты для отладки
                        material_data['groupgoods_thick'] = groupgoods_thick
                        
                        if material_data['is_remainder'] and material_data['warehouseremaindersid']:
                            print(f"🔧 DEBUG: Деловой остаток {material_data['warehouseremaindersid']}: quantity={material_data['quantity']}шт")
                        else:
                            print(f"🔧 DEBUG: Цельный хлыст: quantity={material_data['quantity']}шт")
                        
                        used_materials.append(material_data)
                        
                    # Теперь формируем business_remainders с правильным количеством
                    # Группируем деловые остатки по размеру
                    remainders_by_size = {}  # Ключ: (goodsid, length)
                    
                    for plan in self.optimization_result.cut_plans:
                        remainder = getattr(plan, 'remainder', None)
                        if remainder and remainder > 0:
                            # Определяем goodsid (используем profile_id из первого распила)
                            goodsid = None
                            if plan.cuts and len(plan.cuts) > 0:
                                goodsid = plan.cuts[0].get('profile_id')
                            
                            if goodsid:
                                remainder_key = (goodsid, remainder)
                                if remainder_key not in remainders_by_size:
                                    remainders_by_size[remainder_key] = {
                                        'goodsid': goodsid,
                                        'length': remainder,
                                        'quantity': 0
                                    }
                                # ИСПРАВЛЕНО: Увеличиваем количество на plan.count
                                plan_count = getattr(plan, 'count', 1)
                                remainders_by_size[remainder_key]['quantity'] += plan_count
                    
                    # Формируем итоговый список деловых остатков
                    business_remainders = list(remainders_by_size.values())
                    
                    print(f"🔧 DEBUG: Сформировано {len(used_materials)} использованных материалов и {len(business_remainders)} деловых остатков")
                    
                    # Отладочная информация о формировании business_remainders
                    print("🔧 DEBUG: Детализация business_remainders:")
                    for remainder in business_remainders:
                        print(f"   goodsid={remainder['goodsid']}, length={remainder['length']}, quantity={remainder['quantity']}шт")
                    
                    # Отладочная информация о формировании used_materials
                    print("🔧 DEBUG: Детализация used_materials:")
                    for material in used_materials:
                        print(f"   goodsid={material['goodsid']}, length={material['length']}, quantity={material['quantity']}шт, groupgoods_thick={material.get('groupgoods_thick', 'N/A')}, is_remainder={material.get('is_remainder', False)}, warehouseremaindersid={material.get('warehouseremaindersid', 'N/A')}")
                    
                    print("🔧 DEBUG: Отправляем данные на сервер:")
                    print(f"   grorders_mos_id: {grorders_mos_id}")
                    print(f"   used_materials: {len(used_materials)} записей")
                    print(f"   business_remainders: {len(business_remainders)} записей")
                    
                    # НОВОЕ: Формируем данные для фибергласса
                    used_fiberglass_sheets = []
                    new_fiberglass_remainders = []

                    if self.fabric_optimization_result and self.fabric_optimization_result.layouts:
                        print("🔧 DEBUG: Формирование данных по фиберглассу для отправки...")
                        # 1. Собираем использованные листы и остатки
                        for layout in self.fabric_optimization_result.layouts:
                            sheet = layout.sheet
                            used_sheet_data = {
                                "goodsid": sheet.goodsid,
                                "marking": sheet.marking,
                                "width": sheet.width,
                                "height": sheet.height,
                                "is_remainder": sheet.is_remainder,
                                "remainder_id": sheet.remainder_id,
                                "quantity": 1 # Каждый layout - это один использованный лист/остаток
                            }
                            used_fiberglass_sheets.append(used_sheet_data)

                        # 2. Собираем новые деловые остатки
                        for layout in self.fabric_optimization_result.layouts:
                             for item in layout.get_remnants():
                                new_remainder_data = {
                                    "goodsid": layout.sheet.goodsid, # goodsid от родительского листа
                                    "marking": layout.sheet.marking,
                                    "width": item.width,
                                    "height": item.height,
                                    "quantity": 1 # Каждый остаток - это одна штука
                                }
                                new_fiberglass_remainders.append(new_remainder_data)
                        
                        print(f"   used_fiberglass_sheets: {len(used_fiberglass_sheets)} записей")
                        print(f"   new_fiberglass_remainders: {len(new_fiberglass_remainders)} записей")

                    result = self.api_client.adjust_materials_altawin(
                        grorders_mos_id, 
                        used_materials, 
                        business_remainders,
                        used_fiberglass_sheets,
                        new_fiberglass_remainders
                    )
                    
                    if result.get('success'):
                        outlay_id = result.get('outlay_id')
                        supply_id = result.get('supply_id')
                        transferred_count = result.get('transferred_materials_count', 0)
                        transferred_records = result.get('transferred_records_count', 0)

                        self.status_bar.showMessage(f"Материалы скорректированы")

                        # Показываем информацию о созданных документах
                        info_msg = (
                            f"Материалы успешно скорректированы!\n\n"
                            f"Создано новое списание: {outlay_id}\n"
                            f"Создан новый приход: {supply_id}\n\n"
                            f"Добавлено материалов (профили) в списание: {len(used_materials)}\n"
                            f"Добавлено деловых остатков (профили) в приход: {len(business_remainders)}\n"
                            f"Добавлено материалов (фибергласс) в списание: {len(used_fiberglass_sheets)}\n"
                            f"Добавлено деловых остатков (фибергласс) в приход: {len(new_fiberglass_remainders)}\n\n"
                            f"🔄 Перенесено материалов москиток из СЗ конструкций: {transferred_count} типов ({transferred_records} записей из сводной таблицы)"
                        )
                        QMessageBox.information(self, "Корректировка материалов", info_msg)
                    else:
                        error_msg = result.get('error', 'Неизвестная ошибка')
                        QMessageBox.warning(self, "Предупреждение", f"Корректировка материалов не выполнена: {error_msg}")
                        # Не прерываем выполнение, так как результаты оптимизации уже загружены
                        
                except Exception as e:
                    QMessageBox.warning(self, "Предупреждение", f"Ошибка корректировки материалов: {str(e)}\n\nРезультаты оптимизации загружены успешно, но материалы не скорректированы.")
                    self.status_bar.showMessage("Результаты загружены, но ошибка корректировки материалов")

            # ШАГ 3: Автоматическое распределение ячеек
            self._auto_distribute_cells(grorders_mos_id)

            # Показываем итоговое сообщение об успехе
            success_msg = "✅ Результаты оптимизации успешно загружены в таблицы OPTIMIZED_MOS и OPTDETAIL_MOS"
            if adjust_materials:
                success_msg += "\n\n✅ Материалы в Altawin также были скорректированы"
            QMessageBox.information(self, "Успех", success_msg)
            self.status_bar.showMessage("MOS данные успешно загружены")

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка загрузки MOS: {str(e)}")
            self.status_bar.showMessage("Ошибка загрузки MOS данных")
        finally:
            self.upload_mos_to_altawin_button.setEnabled(True)
    
    def _auto_distribute_cells(self, grorders_mos_id):
        """Автоматическое распределение ячеек без подтверждения от пользователя."""
        try:
            self.status_bar.showMessage("Автоматическое распределение ячеек...")

            # Генерируем карту ячеек на основе загруженных данных
            cell_map = self._generate_cell_map()

            if not cell_map:
                QMessageBox.information(self, "Информация", "Нет уникальных проемов для распределения ячеек.")
                self.status_bar.showMessage("Нет данных для распределения ячеек")
                return

            # Вызываем API с сгенерированной картой
            result = self.api_client.distribute_cell_numbers(grorders_mos_id, cell_map=cell_map)

            if result.get("success"):
                processed_items = result.get("processed_items", 0)
                total_time = result.get("performance", {}).get("total_time", 0)
                
                print(f"✅ Распределение ячеек выполнено успешно для {processed_items} проемов за {total_time} сек.")
                self.status_bar.showMessage(f"Ячейки распределены ({processed_items} проемов)")
                
            else:
                error_msg = result.get("error", result.get("message", "Неизвестная ошибка"))
                QMessageBox.warning(self, "Ошибка", f"Ошибка автоматического распределения ячеек:\n{error_msg}")
                self.status_bar.showMessage("Ошибка распределения ячеек")
                
        except Exception as e:
            QMessageBox.critical(self, "Критическая ошибка", f"Критическая ошибка при автоматическом распределении ячеек:\n{str(e)}")
            self.status_bar.showMessage("Критическая ошибка распределения ячеек")

    def _generate_cell_map(self) -> Dict[str, int]:
        """Вернуть общую для GUI и runner детерминированную карту ячеек."""
        cell_map = generate_cell_map(self.profiles or [], self.fabric_details or [])

        if cell_map:
            print(f"✅ Карта ячеек успешно сгенерирована, {len(cell_map)} уникальных записей.")
            # Логируем первые 5 записей для отладки
            for i, (key, value) in enumerate(cell_map.items()):
                if i >= 5: break
                print(f"   - {key}: {value}")

        return cell_map


    def on_distribute_cells_clicked(self):
        """Обработчик нажатия кнопки распределения ячеек"""
        order_ids_text = self.order_id_input.text().strip()
        if not order_ids_text:
            QMessageBox.warning(self, "Ошибка", "Введите grorders_mos_id")
            return

        try:
            grorders_mos_id = int(order_ids_text)
        except ValueError:
            QMessageBox.warning(self, "Ошибка", "grorders_mos_id должен быть целым числом")
            return

        # Подтверждение операции
        reply = QMessageBox.question(
            self,
            "Подтверждение распределения ячеек",
            f"Вы точно хотите распределить ячейки для grorders_mos_id: {grorders_mos_id}?\n\n"
            f"Это обновит номера ячеек для всех уникальных проемов.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        try:
            self.status_bar.showMessage("Распределение ячеек...")
            
            # Вызываем API для распределения ячеек
            result = self.api_client.distribute_cell_numbers(grorders_mos_id)
            
            if result.get("success"):
                processed_items = result.get("processed_items", 0)
                total_time = result.get("performance", {}).get("total_time", 0)
                
                success_msg = (
                    f"✅ Распределение ячеек выполнено успешно!\n\n"
                    f"• Обработано уникальных проемов: {processed_items}\n"
                    f"• Время выполнения: {total_time} сек"
                )
                
                QMessageBox.information(self, "Успех", success_msg)
                self.status_bar.showMessage(f"Ячейки распределены ({processed_items} проемов)")
                
            else:
                error_msg = result.get("error", result.get("message", "Неизвестная ошибка"))
                QMessageBox.warning(self, "Ошибка", f"Ошибка распределения ячеек:\n{error_msg}")
                self.status_bar.showMessage("Ошибка распределения ячеек")
                
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка распределения ячеек:\n{str(e)}")
            self.status_bar.showMessage("Ошибка распределения ячеек")
        finally:
            pass







    def show_optimization_settings(self):
        """Показать настройки оптимизации"""
        dialog = OptimizationSettingsDialog(self, self.optimization_params)
        if dialog.exec_() == QDialog.Accepted:
            # Получаем новые настройки из диалога
            self.optimization_params = dialog.get_settings()
            
            # Обновляем текущие настройки оптимизации
            self.current_settings.blade_width = self.optimization_params['blade_width']
            self.current_settings.min_remainder_length = self.optimization_params['min_remainder_length'] 
            self.current_settings.max_waste_percent = self.optimization_params['max_waste_percent']
            self.current_settings.pair_optimization = self.optimization_params['pair_optimization']
            self.current_settings.use_remainders = self.optimization_params['use_remainders']
            # Новые параметры парной оптимизации
            self.current_settings.pairing_exact_bonus = self.optimization_params.get('pairing_exact_bonus', 3000.0)
            self.current_settings.pairing_partial_bonus = self.optimization_params.get('pairing_partial_bonus', 1000.0)
            self.current_settings.pairing_partial_threshold = self.optimization_params.get('pairing_partial_threshold', 0.7)
            self.current_settings.pairing_new_simple_bonus = self.optimization_params.get('pairing_new_simple_bonus', 150.0)
            
            # Показываем сообщение об успешном сохранении
            QMessageBox.information(self, "Параметры сохранены", 
                "Новые параметры оптимизации сохранены и будут применены при следующем запуске оптимизации.")
    
    def show_api_settings(self):
        """Показать настройки API"""
        dialog = ApiSettingsDialog(self, {})
        if dialog.exec_() == QDialog.Accepted:
            settings = dialog.get_settings()
            # TODO: Применить настройки API
            QMessageBox.information(self, "Настройки API", "Настройки API будут применены в следующей версии")
    
    def show_about(self):
        """Показать информацию о программе"""
        QMessageBox.about(self, "О программе", 
            "Linear Optimizer v1.0\n\n"
            "Система оптимизации линейного распила профилей\n"
            "Разработано на основе Glass Optimizer\n\n"
            "© 2024 Your Company")

    def set_order_id(self, order_id: int):
        """Установить ID заказа (для обратной совместимости)"""
        self.order_id_input.setText(str(order_id))
        self.on_load_data_clicked()
    
    def set_order_ids(self, order_ids: list):
        """Установить несколько ID заказов"""
        order_ids_str = ", ".join(map(str, order_ids))
        self.order_id_input.setText(order_ids_str)
        self.on_load_data_clicked()

    def on_copy_table_clicked(self):
        """Обработчик копирования таблицы в текстовом формате"""
        try:
            if copy_table_to_clipboard(self.results_table):
                self.status_bar.showMessage("✅ Таблица скопирована в буфер обмена")
                QMessageBox.information(self, "Копирование", "Таблица плана распила успешно скопирована в буфер обмена!\n\nТеперь вы можете вставить её в Excel, Word или любой другой документ.")
            else:
                QMessageBox.warning(self, "Ошибка копирования", "Не удалось скопировать таблицу. Возможно, таблица пуста.")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка при копировании таблицы: {str(e)}")
            self.status_bar.showMessage("❌ Ошибка копирования таблицы")

    def on_copy_csv_clicked(self):
        """Обработчик копирования таблицы в формате CSV"""
        try:
            if copy_table_as_csv(self.results_table):
                self.status_bar.showMessage("✅ Таблица скопирована в буфер обмена как CSV")
                QMessageBox.information(self, "Копирование CSV", "Таблица плана распила успешно скопирована в буфер обмена в формате CSV!\n\nТеперь вы можете вставить её в Excel, где она автоматически разделится по столбцам.")
            else:
                QMessageBox.warning(self, "Ошибка копирования", "Не удалось скопировать таблицу как CSV. Возможно, таблица пуста.")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка при копировании таблицы как CSV: {str(e)}")
            self.status_bar.showMessage("❌ Ошибка копирования таблицы как CSV")









    def closeEvent(self, event):
        """Обработка закрытия приложения"""
        reply = QMessageBox.question(self, 'Выход из программы', 
                                   'Вы действительно хотите выйти?',
                                   QMessageBox.Yes | QMessageBox.No, 
                                   QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            event.accept()
        else:
            event.ignore()
