"""
Диалоги для Linear Optimizer
Адаптировано из Glass Optimizer
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QProgressBar, QApplication, QMessageBox,
    QFormLayout, QSpinBox, QCheckBox, QLineEdit, QGroupBox,
    QScrollArea, QWidget
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont
from datetime import datetime
from .config import DIALOG_STYLE


class DebugDialog(QDialog):
    """Диалог отладки загрузки данных"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Отладка загрузки данных")
        self.setModal(False)  # Не модальный, чтобы можно было видеть консоль
        self.setMinimumSize(600, 500)
        
        # Центрирование относительно родительского окна
        if parent:
            parent_geo = parent.geometry()
            x = parent_geo.x() + (parent_geo.width() - 600) // 2
            y = parent_geo.y() + (parent_geo.height() - 500) // 2
            self.setGeometry(x, y, 600, 500)
        
        # Применение темной темы
        self.setStyleSheet(DIALOG_STYLE)
        
        self.init_ui()
        
        # Начальное сообщение
        self.add_step("🚀 Инициализация загрузки данных...")
        
        print("🔧 DEBUG: Диалог отладки инициализирован")

    def init_ui(self):
        """Инициализация интерфейса"""
        layout = QVBoxLayout()
        
        # Заголовок
        title_label = QLabel("Отладка загрузки данных API")
        title_label.setFont(QFont("Arial", 12, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # Область текста
        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setFont(QFont("Consolas", 9))
        layout.addWidget(self.text_area)
        
        # Кнопки
        button_layout = QHBoxLayout()
        
        self.close_btn = QPushButton("Закрыть")
        self.close_btn.clicked.connect(self.close)
        button_layout.addWidget(self.close_btn)
        
        self.clear_btn = QPushButton("Очистить")
        self.clear_btn.clicked.connect(self.clear_log)
        button_layout.addWidget(self.clear_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)

    def add_step(self, message):
        """Добавление шага в лог"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        
        self.text_area.append(formatted_message)
        self.text_area.verticalScrollBar().setValue(
            self.text_area.verticalScrollBar().maximum()
        )
        
        # Убрали QApplication.processEvents() - он может вызывать recursive repaint
        # Интерфейс обновляется автоматически при добавлении текста
        
        print(f"🔧 DEBUG: {formatted_message}")

    def add_success(self, message):
        """Добавление сообщения об успехе"""
        self.add_step(f"✅ {message}")

    def add_error(self, message):
        """Добавление сообщения об ошибке"""
        self.add_step(f"❌ {message}")

    def add_warning(self, message):
        """Добавление предупреждения"""
        self.add_step(f"⚠️ {message}")

    def add_info(self, message):
        """Добавление информационного сообщения"""
        self.add_step(f"ℹ️ {message}")

    def clear_log(self):
        """Очистка лога"""
        self.text_area.clear()
        self.add_step("🧹 Лог очищен")


class ProgressDialog(QDialog):
    """Диалог прогресса оптимизации"""
    
    # Сигнал для thread-safe обновления прогресса
    progress_signal = pyqtSignal(int, str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Выполнение оптимизации")
        self.setModal(True)
        self.setFixedSize(400, 150)
        
        # Центрирование относительно родительского окна
        if parent:
            parent_geo = parent.geometry()
            x = parent_geo.x() + (parent_geo.width() - 400) // 2
            y = parent_geo.y() + (parent_geo.height() - 150) // 2
            self.setGeometry(x, y, 400, 150)
        
        # Применение темной темы
        self.setStyleSheet(DIALOG_STYLE)
        
        self.init_ui()
        
        # Подключаем сигнал для thread-safe обновления
        self.progress_signal.connect(self._update_progress_safe)

    def init_ui(self):
        """Инициализация интерфейса"""
        layout = QVBoxLayout()
        
        # Заголовок
        title_label = QLabel("Выполнение оптимизации...")
        title_label.setFont(QFont("Arial", 12, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # Прогресс бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # Статус
        self.status_label = QLabel("Подготовка к оптимизации...")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        self.setLayout(layout)

    def set_progress(self, value, status_text=None):
        """
        Установка прогресса (thread-safe)
        Используется из фонового потока
        """
        if status_text is None:
            status_text = f"Выполнено {value}%..."
        
        # Отправляем сигнал для thread-safe обновления
        self.progress_signal.emit(int(value), status_text)
    
    def _update_progress_safe(self, value, status_text):
        """
        Thread-safe обновление прогресса
        Выполняется в главном потоке UI
        """
        try:
            self.progress_bar.setValue(value)
            self.status_label.setText(status_text)
            # Убираем processEvents() - он вызывает recursive repaint
        except Exception as e:
            print(f"⚠️ Ошибка обновления прогресса: {e}")

    def closeEvent(self, event):
        """Перехват события закрытия"""
        # Разрешаем закрытие только при завершении (100%)
        current_value = self.progress_bar.value()
        if current_value >= 100:
            event.accept()
        else:
            # Не разрешаем закрывать диалог во время выполнения
            event.ignore()
    
    def force_close(self):
        """Принудительное закрытие диалога"""
        try:
            self.progress_bar.setValue(100)
            self.accept()
        except Exception as e:
            print(f"⚠️ Ошибка закрытия диалога прогресса: {e}")


class OptimizationSettingsDialog(QDialog):
    """Диалог настроек оптимизации"""
    
    def __init__(self, parent=None, current_settings=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки оптимизации")
        self.setModal(True)
        self.setMinimumSize(600, 700)
        
        # Центрирование относительно родительского окна
        if parent:
            parent_geo = parent.geometry()
            x = parent_geo.x() + (parent_geo.width() - 600) // 2
            y = parent_geo.y() + (parent_geo.height() - 700) // 2
            self.setGeometry(x, y, 600, 700)
        
        # Применение темной темы
        self.setStyleSheet(DIALOG_STYLE)
        
        self.current_settings = current_settings or {}
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        """Инициализация интерфейса"""
        layout = QVBoxLayout()

        # Заголовок
        title_label = QLabel("Параметры оптимизации")
        title_label.setFont(QFont("Arial", 12, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # Создаем прокручиваемую область
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Контейнер для содержимого
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)

        # ==================== Параметры для хлыстовой оптимизации ====================
        whip_group = QGroupBox("Параметры для хлыстовой оптимизации")
        whip_layout = QFormLayout()

        # Ширина распила
        self.blade_width = QSpinBox()
        self.blade_width.setRange(1, 20)
        self.blade_width.setSuffix(" мм")
        whip_layout.addRow("Ширина распила:", self.blade_width)

        # Минимальный остаток
        self.min_remainder_length = QSpinBox()
        self.min_remainder_length.setRange(10, 10000)
        self.min_remainder_length.setSuffix(" мм")
        whip_layout.addRow("Минимальный остаток:", self.min_remainder_length)

        # Максимальный отход
        self.max_waste_percent = QSpinBox()
        self.max_waste_percent.setRange(1, 50)
        self.max_waste_percent.setSuffix(" %")
        whip_layout.addRow("Максимальный отход:", self.max_waste_percent)

        # Парная оптимизация
        self.pair_optimization = QCheckBox("Парная оптимизация")
        whip_layout.addRow(self.pair_optimization)

        # Использование склада остатков
        self.use_remainders = QCheckBox("Использовать склад остатков")
        whip_layout.addRow(self.use_remainders)

        # Минимальный отход (мм)
        self.min_trash_mm = QSpinBox()
        self.min_trash_mm.setRange(0, 1000)
        self.min_trash_mm.setSuffix(" мм")
        whip_layout.addRow("Минимальный отход:", self.min_trash_mm)

        # Отступ от начала
        self.begin_indent = QSpinBox()
        self.begin_indent.setRange(0, 1000)
        self.begin_indent.setSuffix(" мм")
        whip_layout.addRow("Отступ от начала:", self.begin_indent)

        # Отступ от конца
        self.end_indent = QSpinBox()
        self.end_indent.setRange(0, 1000)
        self.end_indent.setSuffix(" мм")
        whip_layout.addRow("Отступ от конца:", self.end_indent)

        whip_group.setLayout(whip_layout)
        content_layout.addWidget(whip_group)

        # ==================== Параметры для плоскостной оптимизации ====================
        planar_group = QGroupBox("Параметры для плоскостной оптимизации")
        planar_layout = QFormLayout()

        # Минимальная ширина для деловых остатков
        self.min_remainder_width = QSpinBox()
        self.min_remainder_width.setRange(10, 10000)
        self.min_remainder_width.setValue(500)
        self.min_remainder_width.setSuffix(" мм")
        planar_layout.addRow("Минимальная ширина для деловых остатков:", self.min_remainder_width)

        # Минимальная высота для деловых остатков
        self.min_remainder_height = QSpinBox()
        self.min_remainder_height.setRange(10, 10000)
        self.min_remainder_height.setValue(500)
        self.min_remainder_height.setSuffix(" мм")
        planar_layout.addRow("Минимальная высота для деловых остатков:", self.min_remainder_height)

        # Ширина реза
        self.planar_cut_width = QSpinBox()
        self.planar_cut_width.setRange(1, 50)
        self.planar_cut_width.setValue(1)
        self.planar_cut_width.setSuffix(" мм")
        planar_layout.addRow("Ширина реза:", self.planar_cut_width)

        # Отступы для листа со всех сторон
        self.sheet_indent = QSpinBox()
        self.sheet_indent.setRange(0, 1000)
        self.sheet_indent.setValue(15)
        self.sheet_indent.setSuffix(" мм")
        planar_layout.addRow("Отступы для листа со всех сторон:", self.sheet_indent)

        # Отступы для делового остатка со всех сторон
        self.remainder_indent = QSpinBox()
        self.remainder_indent.setRange(0, 1000)
        self.remainder_indent.setValue(15)
        self.remainder_indent.setSuffix(" мм")
        planar_layout.addRow("Отступы для делового остатка со всех сторон:", self.remainder_indent)

        # Максимальная процент отхода
        self.planar_max_waste_percent = QSpinBox()
        self.planar_max_waste_percent.setRange(1, 50)
        self.planar_max_waste_percent.setValue(5)
        self.planar_max_waste_percent.setSuffix(" %")
        planar_layout.addRow("Максимальная процент отхода:", self.planar_max_waste_percent)

        planar_group.setLayout(planar_layout)
        content_layout.addWidget(planar_group)

        # Добавляем растяжение в конце
        content_layout.addStretch()

        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)

        # Кнопки
        button_layout = QHBoxLayout()

        self.ok_btn = QPushButton("OK")
        self.ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.ok_btn)

        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        self.reset_btn = QPushButton("По умолчанию")
        self.reset_btn.clicked.connect(self.reset_defaults)
        button_layout.addWidget(self.reset_btn)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def load_settings(self):
        """Загрузка текущих настроек"""
        # Параметры хлыстовой оптимизации
        self.blade_width.setValue(self.current_settings.get('blade_width', 5))
        self.min_remainder_length.setValue(self.current_settings.get('min_remainder_length', 300))
        self.max_waste_percent.setValue(self.current_settings.get('max_waste_percent', 15))
        self.pair_optimization.setChecked(self.current_settings.get('pair_optimization', True))
        self.use_remainders.setChecked(self.current_settings.get('use_remainders', True))
        self.min_trash_mm.setValue(self.current_settings.get('min_trash_mm', 50))
        self.begin_indent.setValue(self.current_settings.get('begin_indent', 10))
        self.end_indent.setValue(self.current_settings.get('end_indent', 10))

        # Параметры плоскостной оптимизации
        self.min_remainder_width.setValue(self.current_settings.get('min_remainder_width', 500))
        self.min_remainder_height.setValue(self.current_settings.get('min_remainder_height', 500))
        self.planar_cut_width.setValue(self.current_settings.get('planar_cut_width', 1))
        self.sheet_indent.setValue(self.current_settings.get('sheet_indent', 15))
        self.remainder_indent.setValue(self.current_settings.get('remainder_indent', 15))
        self.planar_max_waste_percent.setValue(self.current_settings.get('planar_max_waste_percent', 5))

    def reset_defaults(self):
        """Сброс к значениям по умолчанию"""
        # Параметры хлыстовой оптимизации
        self.blade_width.setValue(5)  # По умолчанию 5
        self.min_remainder_length.setValue(300)  # По умолчанию 300
        self.max_waste_percent.setValue(15)
        self.pair_optimization.setChecked(True)  # По умолчанию да
        self.use_remainders.setChecked(True)  # По умолчанию да
        self.min_trash_mm.setValue(50)
        self.begin_indent.setValue(10)
        self.end_indent.setValue(10)

        # Параметры плоскостной оптимизации
        self.min_remainder_width.setValue(500)  # По умолчанию 500
        self.min_remainder_height.setValue(500)  # По умолчанию 500
        self.planar_cut_width.setValue(1)  # По умолчанию 1
        self.sheet_indent.setValue(15)  # По умолчанию 15
        self.remainder_indent.setValue(15)  # По умолчанию 15
        self.planar_max_waste_percent.setValue(5)  # По умолчанию 5

    def get_settings(self):
        """Получение настроек"""
        return {
            # Параметры хлыстовой оптимизации
            'blade_width': self.blade_width.value(),
            'min_remainder_length': self.min_remainder_length.value(),
            'max_waste_percent': self.max_waste_percent.value(),
            'pair_optimization': self.pair_optimization.isChecked(),
            'use_remainders': self.use_remainders.isChecked(),
            'min_trash_mm': self.min_trash_mm.value(),
            'begin_indent': self.begin_indent.value(),
            'end_indent': self.end_indent.value(),

            # Параметры плоскостной оптимизации
            'min_remainder_width': self.min_remainder_width.value(),
            'min_remainder_height': self.min_remainder_height.value(),
            'planar_cut_width': self.planar_cut_width.value(),
            'sheet_indent': self.sheet_indent.value(),
            'remainder_indent': self.remainder_indent.value(),
            'planar_max_waste_percent': self.planar_max_waste_percent.value()
        }


class ApiSettingsDialog(QDialog):
    """Диалог настроек API"""
    
    def __init__(self, parent=None, current_settings=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки API")
        self.setModal(True)
        self.setMinimumSize(400, 250)
        
        # Центрирование относительно родительского окна
        if parent:
            parent_geo = parent.geometry()
            x = parent_geo.x() + (parent_geo.width() - 400) // 2
            y = parent_geo.y() + (parent_geo.height() - 250) // 2
            self.setGeometry(x, y, 400, 250)
        
        # Применение темной темы
        self.setStyleSheet(DIALOG_STYLE)
        
        self.current_settings = current_settings or {}
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        """Инициализация интерфейса"""
        layout = QVBoxLayout()
        
        # Заголовок
        title_label = QLabel("Настройки подключения к API")
        title_label.setFont(QFont("Arial", 12, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # Форма настроек
        form_layout = QFormLayout()
        
        # URL сервера
        self.server_url = QLineEdit()
        self.server_url.setPlaceholderText("http://localhost:8000")
        form_layout.addRow("URL сервера:", self.server_url)
        
        # Таймаут
        self.timeout = QSpinBox()
        self.timeout.setRange(1, 300)
        self.timeout.setSuffix(" сек")
        form_layout.addRow("Таймаут:", self.timeout)
        
        # Максимальное количество попыток
        self.max_retries = QSpinBox()
        self.max_retries.setRange(1, 10)
        form_layout.addRow("Макс. попыток:", self.max_retries)
        
        layout.addLayout(form_layout)
        
        # Кнопки
        button_layout = QHBoxLayout()
        
        self.test_btn = QPushButton("Тест соединения")
        self.test_btn.clicked.connect(self.test_connection)
        button_layout.addWidget(self.test_btn)
        
        button_layout.addStretch()
        
        self.ok_btn = QPushButton("OK")
        self.ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.ok_btn)
        
        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)

    def load_settings(self):
        """Загрузка текущих настроек"""
        self.server_url.setText(self.current_settings.get('server_url', 'http://localhost:8000'))
        self.timeout.setValue(self.current_settings.get('timeout', 30))
        self.max_retries.setValue(self.current_settings.get('max_retries', 3))

    def test_connection(self):
        """Тест соединения с API"""
        # TODO: Реализовать тест соединения
        QMessageBox.information(self, "Тест соединения", "Функция тестирования будет реализована позже")

    def get_settings(self):
        """Получение настроек"""
        return {
            'server_url': self.server_url.text().strip(),
            'timeout': self.timeout.value(),
            'max_retries': self.max_retries.value()
        }