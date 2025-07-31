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
    QAction, QApplication
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt5.QtGui import QFont, QIcon, QShowEvent
import sys
import threading
from datetime import datetime
import functools
import requests
import os
import json
import logging

# Импорты для модульной архитектуры
from core.api_client import get_api_client
from core.optimizer import LinearOptimizer, OptimizationSettings
from core.models import Profile, Stock, OptimizationResult, StockRemainder, StockMaterial
from .table_widgets import (
    _create_text_item, _create_numeric_item, setup_table_columns,
    fill_profiles_table, fill_stock_table, fill_optimization_results_table,
    fill_stock_remainders_table, fill_stock_materials_table,
    update_table_column_widths, clear_table, enable_table_sorting
)
from .dialogs import DebugDialog, ProgressDialog, OptimizationSettingsDialog, ApiSettingsDialog
from .config import MAIN_WINDOW_STYLE, TAB_STYLE, SPECIAL_BUTTON_STYLES, WIDGET_CONFIGS, COLORS

# Настройка логирования
logger = logging.getLogger(__name__)


class LinearOptimizerWindow(QMainWindow):
    """Главное окно приложения Linear Optimizer"""
    
    # Сигналы для thread-safe коммуникации
    debug_step_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str, str, str)  # title, message, icon
    success_signal = pyqtSignal()
    data_loaded_signal = pyqtSignal(list, dict)  # profiles, stock_data
    restore_button_signal = pyqtSignal()
    
    # Сигналы для оптимизации
    optimization_result_signal = pyqtSignal(object)  # OptimizationResult
    optimization_error_signal = pyqtSignal(str)
    close_progress_signal = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        
        # Инициализация данных
        self.api_client = get_api_client()
        self.optimizer = LinearOptimizer()
        self.current_order_id = None
        self.profiles = []
        self.stocks = []  # Для обратной совместимости
        self.stock_remainders = []  # Остатки со склада
        self.stock_materials = []   # Цельные материалы со склада
        self.optimization_result = None
        self.current_settings = OptimizationSettings()
        
        # Инициализация диалогов
        self.debug_dialog = None
        self.progress_dialog = None
        
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
        
        # Меню Настройки
        settings_menu = menubar.addMenu("Настройки")
        
        optimization_settings_action = QAction("Параметры оптимизации", self)
        optimization_settings_action.triggered.connect(self.show_optimization_settings)
        settings_menu.addAction(optimization_settings_action)
        
        api_settings_action = QAction("Настройки API", self)
        api_settings_action.triggered.connect(self.show_api_settings)
        settings_menu.addAction(api_settings_action)
        
        # Меню Помощь
        help_menu = menubar.addMenu("Помощь")
        
        about_action = QAction("О программе", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)



    def create_order_data_tab(self):
        """Создание вкладки данных заказа"""
        order_tab = QWidget()
        layout = QVBoxLayout(order_tab)

        # Верхняя часть - информация о заказе
        top_group = self.create_order_info_group()
        layout.addWidget(top_group)
        
        # Средняя часть - данные (профили и склады)
        middle_splitter = QSplitter(Qt.Horizontal)
        
        # Левая часть - профили для распила
        left_group = self.create_profiles_group()
        middle_splitter.addWidget(left_group)
        
        # Правая часть - склады (разделенные)
        right_group = self.create_stock_groups()
        middle_splitter.addWidget(right_group)
        
        middle_splitter.setSizes([500, 900])
        layout.addWidget(middle_splitter)
        
        # Нижняя часть - параметры оптимизации
        params_group = self.create_optimization_params_group()
        layout.addWidget(params_group)
        
        self.tabs.addTab(order_tab, "📊 Данные заказа")

    def create_order_info_group(self):
        """Создание группы информации о заказе"""
        group = QGroupBox("Информация о заказе")
        layout = QVBoxLayout(group)

        # Поля ввода и загрузки
        input_layout = QHBoxLayout()
        
        input_layout.addWidget(QLabel("ID заказа:"))
        self.order_id_input = QLineEdit()
        self.order_id_input.setPlaceholderText("Введите номер заказа")
        self.order_id_input.setMaximumWidth(150)
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

    def create_profiles_group(self):
        """Создание группы профилей для распила"""
        group = QGroupBox("Профили для распила")
        layout = QVBoxLayout(group)

        # Таблица профилей
        self.profiles_table = QTableWidget()
        setup_table_columns(self.profiles_table, [
            'Элемент', 'Артикул профиля', 'Длина (мм)', 'Количество'
        ])
        
        # Включаем сортировку
        enable_table_sorting(self.profiles_table, True)
        self.profiles_table.setMinimumHeight(300)
        layout.addWidget(self.profiles_table)
        
        return group

    def create_stock_groups(self):
        """Создание групп складов (остатки и материалы)"""
        # Основной контейнер
        main_widget = QWidget()
        layout = QVBoxLayout(main_widget)
        
        # Создаем вертикальный сплиттер для двух таблиц складов
        splitter = QSplitter(Qt.Vertical)
        
        # Группа остатков на складе
        remainders_group = QGroupBox("Склад остатков")
        remainders_layout = QVBoxLayout(remainders_group)
        
        self.stock_remainders_table = QTableWidget()
        setup_table_columns(self.stock_remainders_table, [
            'Наименование', 'Длина (мм)', 'Количество палок'
        ])
        enable_table_sorting(self.stock_remainders_table, True)
        self.stock_remainders_table.setMinimumHeight(200)
        remainders_layout.addWidget(self.stock_remainders_table)
        
        # Группа материалов на складе
        materials_group = QGroupBox("Склад материалов")
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

    def create_optimization_params_group(self):
        """Создание группы параметров оптимизации"""
        params_group = QGroupBox("Параметры оптимизации")
        layout = QFormLayout()
        
        # Минимальная длина остатка
        self.min_remainder_length = QSpinBox()
        self.min_remainder_length.setRange(10, 10000)
        self.min_remainder_length.setValue(300)
        self.min_remainder_length.setSuffix(" мм")
        layout.addRow("Мин. длина остатка:", self.min_remainder_length)
        
        # Толщина пропила
        self.blade_width = QSpinBox()
        self.blade_width.setRange(1, 20)
        self.blade_width.setValue(3)
        self.blade_width.setSuffix(" мм")
        layout.addRow("Толщина пропила:", self.blade_width)
        
        # Максимальный процент отходов
        self.max_waste_percent = QSpinBox()
        self.max_waste_percent.setRange(1, 50)
        self.max_waste_percent.setValue(15)
        self.max_waste_percent.setSuffix(" %")
        self.max_waste_percent.setStyleSheet(WIDGET_CONFIGS["target_waste_percent"])
        layout.addRow("🎯 Макс. % отходов:", self.max_waste_percent)
        
        # Использование остатков
        self.use_remainders = QCheckBox("Использовать остатки со склада")
        self.use_remainders.setChecked(True)
        layout.addRow(self.use_remainders)
        
        # Оптимизация порядка
        self.optimize_order = QCheckBox("Оптимизировать порядок распила")
        self.optimize_order.setChecked(True)
        layout.addRow(self.optimize_order)
        
        # Кнопки на одном уровне
        buttons_layout = QHBoxLayout()
        
        # Кнопка сохранения настроек (слева)
        self.save_settings_button = QPushButton("💾 Сохранить параметры")
        self.save_settings_button.clicked.connect(self.on_save_settings_clicked)
        self.save_settings_button.setStyleSheet(SPECIAL_BUTTON_STYLES["save_settings"])
        buttons_layout.addWidget(self.save_settings_button)
        
        # Добавляем растяжку между кнопками
        buttons_layout.addStretch()
        
        # Кнопка оптимизации (справа)
        self.optimize_button = QPushButton("🚀 Запустить оптимизацию")
        self.optimize_button.clicked.connect(self.on_optimize_clicked)
        self.optimize_button.setEnabled(False)
        self.optimize_button.setStyleSheet(SPECIAL_BUTTON_STYLES["optimize"])
        buttons_layout.addWidget(self.optimize_button)
        
        layout.addRow(buttons_layout)
        
        params_group.setLayout(layout)
        return params_group

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
            'Хлыст (ID)', 'Длина хлыста (мм)', 'Распилы', 'Отход (мм)', 'Отход (%)'
        ])
        
        # Включаем сортировку
        enable_table_sorting(self.results_table, True)
        self.results_table.setMinimumHeight(400)
        results_layout.addWidget(self.results_table)
        
        results_group.setLayout(results_layout)
        layout.addWidget(results_group)
        
        self.tabs.addTab(results_tab, "📈 Результаты оптимизации")

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
        
        stats_layout.addLayout(right_layout)
        layout.addLayout(stats_layout)
        
        # Кнопка загрузки данных в Altawin
        upload_layout = QHBoxLayout()
        upload_layout.addStretch()
        
        self.upload_to_altawin_button = QPushButton("📤 Загрузить результаты в Altawin")
        self.upload_to_altawin_button.setStyleSheet(SPECIAL_BUTTON_STYLES["upload"])
        self.upload_to_altawin_button.clicked.connect(self.on_save_results)
        self.upload_to_altawin_button.setEnabled(False)
        
        upload_layout.addWidget(self.upload_to_altawin_button)
        upload_layout.addStretch()
        
        layout.addLayout(upload_layout)
        
        return group

    # ========== МЕТОДЫ ЗАГРУЗКИ ДАННЫХ ==========
    
    def on_load_data_clicked(self):
        """Обработчик загрузки данных с API"""
        order_id = self.order_id_input.text().strip()
        if not order_id:
            QMessageBox.warning(self, "Ошибка", "Введите номер заказа")
            return
        
        try:
            order_id = int(order_id)
        except ValueError:
            QMessageBox.warning(self, "Ошибка", "ID заказа должен быть числом")
            return
        
        # Блокируем кнопку
        self.load_data_button.setEnabled(False)
        self.load_data_button.setText("Загрузка...")
        
        # Открываем диалог отладки
        self.debug_dialog = DebugDialog(self)
        self.debug_dialog.show()
        
        # Запускаем загрузку в отдельном потоке
        def load_data():
            try:
                self._add_debug_step(f"🔄 Загрузка данных для заказа {order_id}...")
                
                # Загружаем профили
                self._add_debug_step("📋 Загрузка профилей...")
                profiles = self.api_client.get_profiles(order_id)
                self._add_debug_step(f"✅ Загружено {len(profiles)} профилей")
                
                # Получаем уникальные артикулы профилей
                profile_codes = list(set(profile.profile_code for profile in profiles))
                
                # Загружаем остатки со склада
                self._add_debug_step("📦 Загрузка остатков со склада...")
                stock_remainders = self.api_client.get_stock_remainders(profile_codes)
                self._add_debug_step(f"✅ Загружено {len(stock_remainders)} остатков")
                
                # Загружаем материалы со склада
                self._add_debug_step("📦 Загрузка материалов со склада...")
                stock_materials = self.api_client.get_stock_materials(profile_codes)
                self._add_debug_step(f"✅ Загружено {len(stock_materials)} материалов")
                
                # Обновляем данные в UI
                self.data_loaded_signal.emit(profiles, {'remainders': stock_remainders, 'materials': stock_materials})
                self._add_debug_step("🎉 Загрузка данных завершена успешно!")
                self.success_signal.emit()
                
            except Exception as e:
                self._add_debug_step(f"❌ Ошибка загрузки: {e}")
                self.error_signal.emit("Ошибка загрузки", str(e), "critical")
            finally:
                self.restore_button_signal.emit()
        
        # Запускаем в потоке
        thread = threading.Thread(target=load_data, daemon=True)
        thread.start()

    # ========== МЕТОДЫ ОПТИМИЗАЦИИ ==========
    
    def on_optimize_clicked(self):
        """Обработчик кнопки оптимизации"""
        if not self.profiles:
            QMessageBox.warning(self, "Предупреждение", "Сначала загрузите данные заказа")
            return
        
        # Блокируем кнопку
        self.optimize_button.setEnabled(False)
        self.optimize_button.setText("Оптимизация...")
        
        # Показываем диалог прогресса
        self.progress_dialog = ProgressDialog(self)
        self.progress_dialog.show()
        
        # Собираем параметры оптимизации
        self.current_settings.min_remainder_length = self.min_remainder_length.value()
        self.current_settings.blade_width = self.blade_width.value()
        self.current_settings.max_waste_percent = self.max_waste_percent.value()
        self.current_settings.use_remainders = self.use_remainders.isChecked()
        self.current_settings.optimize_order = self.optimize_order.isChecked()
        
        # Запускаем оптимизацию в отдельном потоке
        def run_optimization():
            try:
                def progress_callback(percent):
                    if self.progress_dialog:
                        self.progress_dialog.set_progress(percent)
                
                # Запуск оптимизации
                result = self.optimizer.optimize(
                    profiles=self.profiles,
                    stocks=self.stocks,
                    settings=self.current_settings,
                    progress_fn=progress_callback
                )
                
                if result and result.success:
                    self.optimization_result = result
                    self.optimization_result_signal.emit(result)
                else:
                    error_msg = "Оптимизация не дала результатов"
                    if result and hasattr(result, 'message'):
                        error_msg = result.message
                    self.optimization_error_signal.emit(error_msg)
                    
            except Exception as e:
                error_msg = f"Ошибка оптимизации: {str(e)}"
                self.optimization_error_signal.emit(error_msg)
            finally:
                self.close_progress_signal.emit()
        
        # Запускаем в отдельном потоке
        thread = threading.Thread(target=run_optimization, daemon=True)
        thread.start()

    def on_save_results(self):
        """Сохранение результатов в Altawin"""
        if not self.optimization_result:
            QMessageBox.warning(self, "Предупреждение", "Нет результатов для сохранения")
            return
        
        # Диалог подтверждения
        reply = QMessageBox.question(
            self, 
            "Подтверждение сохранения", 
            f"Вы точно хотите сохранить результаты оптимизации в Altawin?\n\n"
            f"Заказ: {self.current_order_id}\n"
            f"Количество хлыстов: {len(self.optimization_result.cut_plans)}\n"
            f"Эффективность: {100 - self.optimization_result.get_statistics()['waste_percent']:.1f}%",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                success = self.api_client.upload_optimization_result(
                    self.current_order_id,
                    self.optimization_result
                )
                
                if success:
                    QMessageBox.information(self, "Успех", "Результаты успешно сохранены в Altawin")
                    self.status_bar.showMessage("Результаты сохранены")
                
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка сохранения: {str(e)}")

    def on_save_settings_clicked(self):
        """Сохранение текущих параметров оптимизации"""
        # Здесь можно реализовать сохранение настроек в файл
        settings = {
            'min_remainder_length': self.min_remainder_length.value(),
            'blade_width': self.blade_width.value(),
            'max_waste_percent': self.max_waste_percent.value(),
            'use_remainders': self.use_remainders.isChecked(),
            'optimize_order': self.optimize_order.isChecked()
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
    
    def _update_tables_safe(self, profiles, stock_data):
        """Thread-safe обновление таблиц"""
        try:
            # Сохраняем данные
            self.profiles = profiles
            self.stock_remainders = stock_data.get('remainders', [])
            self.stock_materials = stock_data.get('materials', [])
            self.current_order_id = int(self.order_id_input.text().strip()) if self.order_id_input.text().strip().isdigit() else None
            
            # Обновляем таблицы
            fill_profiles_table(self.profiles_table, [p.__dict__ for p in profiles])
            fill_stock_remainders_table(self.stock_remainders_table, [r.__dict__ for r in self.stock_remainders])
            fill_stock_materials_table(self.stock_materials_table, [m.__dict__ for m in self.stock_materials])
            
            # Обновляем информацию о заказе
            total_stock_items = len(self.stock_remainders) + len(self.stock_materials)
            self.order_info_label.setText(
                f"Заказ {self.current_order_id}: {len(profiles)} профилей, "
                f"{len(self.stock_remainders)} остатков, {len(self.stock_materials)} материалов"
            )
            
            # Активируем кнопку оптимизации
            self.optimize_button.setEnabled(True)
            
            # Автоматически подгоняем ширину столбцов
            QTimer.singleShot(500, lambda: [
                update_table_column_widths(self.profiles_table),
                update_table_column_widths(self.stock_remainders_table),
                update_table_column_widths(self.stock_materials_table)
            ])
            
        except Exception as e:
            print(f"❌ Ошибка обновления таблиц: {e}")
    
    def _restore_button_safe(self):
        """Thread-safe восстановление кнопки"""
        self.load_data_button.setEnabled(True)
        self.load_data_button.setText("Загрузить данные")
    
    def _handle_optimization_result(self, result):
        """Обработка результата оптимизации"""
        self.optimization_result = result
        
        # Восстанавливаем кнопку
        self.optimize_button.setEnabled(True)
        self.optimize_button.setText("🚀 Запустить оптимизацию")
        
        # Обновляем статистику
        self._update_statistics(result)
        
        # Обновляем таблицу результатов
        fill_optimization_results_table(self.results_table, result.cut_plans)
        
        # Активируем кнопку загрузки в Altawin
        self.upload_to_altawin_button.setEnabled(True)
        
        # Переключаемся на вкладку результатов
        self.tabs.setCurrentIndex(1)
        
        print(f"✅ Оптимизация завершена! Использовано хлыстов: {len(result.cut_plans)}")
    
    def _handle_optimization_error(self, error_msg):
        """Обработка ошибки оптимизации"""
        # Восстанавливаем кнопку
        self.optimize_button.setEnabled(True)
        self.optimize_button.setText("🚀 Запустить оптимизацию")
        
        # Показываем ошибку
        print(f"❌ Ошибка оптимизации: {error_msg}")
        QMessageBox.critical(self, "Ошибка оптимизации", f"Произошла ошибка во время выполнения оптимизации:\n\n{error_msg}")
    
    def _close_progress_dialog(self):
        """Закрытие диалога прогресса"""
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
    
    def _update_statistics(self, result):
        """Обновление статистики"""
        stats = result.get_statistics()
        
        self.stats_total_stocks.setText(str(stats['total_stocks']))
        self.stats_total_cuts.setText(str(stats['total_cuts']))
        self.stats_total_length.setText(f"{stats['total_length'] / 1000:.1f} м")
        self.stats_waste_length.setText(f"{stats['total_waste'] / 1000:.1f} м")
        self.stats_waste_percent.setText(f"{stats['waste_percent']:.2f} %")
        self.stats_efficiency.setText(f"{100 - stats['waste_percent']:.2f} %")

    # ========== МЕТОДЫ МЕНЮ ==========
    
    def new_optimization(self):
        """Начать новую оптимизацию"""
        self.order_id_input.clear()
        clear_table(self.profiles_table)
        clear_table(self.stock_remainders_table)
        clear_table(self.stock_materials_table)
        clear_table(self.results_table)
        self.optimization_result = None
        self.upload_to_altawin_button.setEnabled(False)
        self.optimize_button.setEnabled(False)
        self.order_info_label.setText("<заказ не загружен>")
        self.status_bar.showMessage("Готов к работе")
        self.tabs.setCurrentIndex(0)
    
    def show_optimization_settings(self):
        """Показать настройки оптимизации"""
        current_settings = {
            'min_remainder_length': self.min_remainder_length.value(),
            'blade_width': self.blade_width.value(),
            'max_waste_percent': self.max_waste_percent.value(),
            'use_remainders': self.use_remainders.isChecked(),
            'optimize_order': self.optimize_order.isChecked()
        }
        
        dialog = OptimizationSettingsDialog(self, current_settings)
        if dialog.exec_() == QDialog.Accepted:
            settings = dialog.get_settings()
            
            # Применяем новые настройки
            self.min_remainder_length.setValue(settings['min_remainder_length'])
            self.blade_width.setValue(settings['blade_width'])
            self.max_waste_percent.setValue(settings['max_waste_percent'])
            self.use_remainders.setChecked(settings['use_remainders'])
            self.optimize_order.setChecked(settings['optimize_order'])
    
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
        """Установить ID заказа"""
        self.order_id_input.setText(str(order_id))
        self.on_load_data_clicked()

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