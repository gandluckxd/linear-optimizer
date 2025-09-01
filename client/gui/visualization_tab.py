#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Вкладка визуализации 2D раскроя фибергласса
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QScrollArea, QFrame, QSplitter, QGroupBox, QPushButton,
    QSlider, QCheckBox, QSpinBox, QFormLayout
)
from PyQt5.QtCore import Qt, QRectF, QPointF, QTimer
from PyQt5.QtGui import QPainter, QPen, QBrush, QColor, QFont, QTransform
import math
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from core.models import FiberglassOptimizationResult, FiberglassRollLayout, PlacedFiberglassItem


@dataclass
class VisualizationSettings:
    """Настройки визуализации"""
    scale: float = 1.0
    show_grid: bool = True
    show_labels: bool = True
    show_dimensions: bool = False
    grid_size: int = 50  # Размер сетки в пикселях
    margin: int = 20    # Отступы от краев
    roll_spacing: int = 50  # Расстояние между рулонами


class FiberglassCanvas(QFrame):
    """Холст для отрисовки раскладки фибергласса"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(800, 600)
        self.setFrameStyle(QFrame.Box)

        # Данные для отрисовки
        self.layout: Optional[FiberglassRollLayout] = None
        self.settings = VisualizationSettings()

        # Цвета для разных типов элементов
        self.colors = {
            'detail': QColor(100, 150, 255),      # Синий для деталей
            'remainder': QColor(150, 255, 150),   # Зеленый для деловых остатков
            'waste': QColor(255, 100, 100),       # Красный для отходов
            'background': QColor(240, 240, 240),  # Фон
            'grid': QColor(200, 200, 200),        # Сетка
            'text': QColor(50, 50, 50),           # Текст
            'roll_border': QColor(0, 0, 0)        # Граница рулона
        }

        # Шрифты
        self.fonts = {
            'label': QFont('Arial', 8),
            'dimension': QFont('Arial', 7)
        }

    def set_layout(self, layout: FiberglassRollLayout):
        """Установить раскладку для отрисовки"""
        self.layout = layout
        self.update()

    def set_settings(self, settings: VisualizationSettings):
        """Установить настройки визуализации"""
        self.settings = settings
        self.update()

    def paintEvent(self, event):
        """Отрисовка раскладки"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Очищаем фон
        painter.fillRect(self.rect(), self.colors['background'])

        if not self.layout:
            self._draw_empty_state(painter)
            return

        # Вычисляем размеры для отрисовки
        roll_width = self.layout.sheet.width
        roll_height = self.layout.sheet.height

        # Масштабируем размеры
        scaled_width = roll_width * self.settings.scale
        scaled_height = roll_height * self.settings.scale

        # Центрируем рулон на холсте
        offset_x = (self.width() - scaled_width) / 2
        offset_y = (self.height() - scaled_height) / 2

        # Рисуем сетку
        if self.settings.show_grid:
            self._draw_grid(painter, offset_x, offset_y, scaled_width, scaled_height)

        # Рисуем границы рулона
        self._draw_roll_border(painter, offset_x, offset_y, scaled_width, scaled_height)

        # Рисуем размещенные элементы
        for item in self.layout.placed_items:
            self._draw_item(painter, item, offset_x, offset_y, self.settings.scale)

        # Рисуем информацию о рулоне
        self._draw_roll_info(painter, offset_x, offset_y, scaled_width, scaled_height)

    def _draw_empty_state(self, painter: QPainter):
        """Отрисовка пустого состояния"""
        painter.setPen(QPen(self.colors['text']))
        painter.setFont(QFont('Arial', 12))
        painter.drawText(
            self.rect(),
            Qt.AlignCenter,
            "Выберите рулон для просмотра раскладки"
        )

    def _draw_grid(self, painter: QPainter, offset_x: float, offset_y: float,
                   width: float, height: float):
        """Отрисовка сетки"""
        painter.setPen(QPen(self.colors['grid'], 1, Qt.DotLine))

        # Вертикальные линии
        x = offset_x
        while x <= offset_x + width:
            painter.drawLine(int(x), int(offset_y), int(x), int(offset_y + height))
            x += self.settings.grid_size

        # Горизонтальные линии
        y = offset_y
        while y <= offset_y + height:
            painter.drawLine(int(offset_x), int(y), int(offset_x + width), int(y))
            y += self.settings.grid_size

    def _draw_roll_border(self, painter: QPainter, offset_x: float, offset_y: float,
                         width: float, height: float):
        """Отрисовка границы рулона"""
        painter.setPen(QPen(self.colors['roll_border'], 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(int(offset_x), int(offset_y), int(width), int(height))

    def _draw_item(self, painter: QPainter, item: PlacedFiberglassItem,
                   offset_x: float, offset_y: float, scale: float):
        """Отрисовка размещенного элемента"""
        # Вычисляем координаты с учетом масштаба
        x = offset_x + item.x * scale
        y = offset_y + item.y * scale
        width = item.width * scale
        height = item.height * scale

        # Выбираем цвет в зависимости от типа
        if item.item_type == 'detail':
            color = self.colors['detail']
            border_color = QColor(50, 100, 200)
        elif item.item_type == 'remainder':
            color = self.colors['remainder']
            border_color = QColor(100, 200, 100)
        else:  # waste
            color = self.colors['waste']
            border_color = QColor(200, 50, 50)

        # Рисуем прямоугольник
        painter.setPen(QPen(border_color, 1))
        painter.setBrush(QBrush(color))
        painter.drawRect(int(x), int(y), int(width), int(height))

        # Рисуем метку если включено
        if self.settings.show_labels and width > 30 and height > 20:
            self._draw_item_label(painter, item, x, y, width, height)

        # Рисуем размеры если включено
        if self.settings.show_dimensions:
            self._draw_item_dimensions(painter, item, x, y, width, height)

    def _draw_item_label(self, painter: QPainter, item: PlacedFiberglassItem,
                        x: float, y: float, width: float, height: float):
        """Отрисовка метки элемента"""
        painter.setPen(QPen(self.colors['text']))
        painter.setFont(self.fonts['label'])

        label_text = ""
        if item.item_type == 'detail' and item.detail:
            label_text = f"{item.detail.marking}"
            if item.is_rotated:
                label_text += " ↻"
        elif item.item_type == 'remainder':
            label_text = "ОСТ"
        elif item.item_type == 'waste':
            label_text = "ОТХ"

        if label_text:
            # Центрируем текст
            text_rect = painter.fontMetrics().boundingRect(label_text)
            text_x = x + (width - text_rect.width()) / 2
            text_y = y + (height + text_rect.height()) / 2
            painter.drawText(int(text_x), int(text_y), label_text)

    def _draw_item_dimensions(self, painter: QPainter, item: PlacedFiberglassItem,
                             x: float, y: float, width: float, height: float):
        """Отрисовка размеров элемента"""
        painter.setPen(QPen(self.colors['text'], 1))
        painter.setFont(self.fonts['dimension'])

        # Размеры по ширине
        width_text = f"{item.width:.0f}"
        painter.drawText(int(x + width/2 - 10), int(y - 5), width_text)

        # Размеры по высоте
        height_text = f"{item.height:.0f}"
        painter.save()
        painter.translate(int(x - 5), int(y + height/2))
        painter.rotate(-90)
        painter.drawText(0, 0, height_text)
        painter.restore()

    def _draw_roll_info(self, painter: QPainter, offset_x: float, offset_y: float,
                       width: float, height: float):
        """Отрисовка информации о рулоне"""
        painter.setPen(QPen(self.colors['text']))
        painter.setFont(QFont('Arial', 10, QFont.Bold))

        info_text = ".0f"".1f"".0f"".1f"".1f"".1f"
        painter.drawText(int(offset_x), int(offset_y - 5), info_text)


class VisualizationTab(QWidget):
    """Вкладка визуализации раскроя"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.optimization_result: Optional[FiberglassOptimizationResult] = None
        self.current_roll_index = 0
        self.settings = VisualizationSettings()

        self.init_ui()

    def init_ui(self):
        """Инициализация интерфейса"""
        layout = QVBoxLayout(self)

        # Верхняя панель управления
        self.create_control_panel()
        layout.addWidget(self.control_panel)

        # Основная область с разделителем
        splitter = QSplitter(Qt.Horizontal)

        # Левая панель - настройки и информация
        left_panel = self.create_left_panel()
        splitter.addWidget(left_panel)

        # Правая панель - холст визуализации
        self.canvas = FiberglassCanvas()
        scroll_area = QScrollArea()
        scroll_area.setWidget(self.canvas)
        scroll_area.setWidgetResizable(True)
        splitter.addWidget(scroll_area)

        splitter.setSizes([300, 800])
        layout.addWidget(splitter)

    def create_control_panel(self):
        """Создание панели управления"""
        self.control_panel = QGroupBox("Управление визуализацией")
        layout = QHBoxLayout(self.control_panel)

        # Выбор рулона
        layout.addWidget(QLabel("Рулон:"))
        self.roll_combo = QComboBox()
        self.roll_combo.currentIndexChanged.connect(self.on_roll_changed)
        layout.addWidget(self.roll_combo)

        layout.addStretch()

        # Кнопки масштаба
        self.zoom_in_btn = QPushButton("🔍+")
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        layout.addWidget(self.zoom_in_btn)

        self.zoom_out_btn = QPushButton("🔍-")
        self.zoom_out_btn.clicked.connect(self.zoom_out)
        layout.addWidget(self.zoom_out_btn)

        self.fit_btn = QPushButton("📐 Вписать")
        self.fit_btn.clicked.connect(self.fit_to_view)
        layout.addWidget(self.fit_btn)

    def create_left_panel(self):
        """Создание левой панели с настройками"""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Группа настроек отображения
        display_group = QGroupBox("Настройки отображения")
        display_layout = QVBoxLayout(display_group)

        self.show_grid_cb = QCheckBox("Показывать сетку")
        self.show_grid_cb.setChecked(self.settings.show_grid)
        self.show_grid_cb.stateChanged.connect(self.on_settings_changed)
        display_layout.addWidget(self.show_grid_cb)

        self.show_labels_cb = QCheckBox("Показывать метки")
        self.show_labels_cb.setChecked(self.settings.show_labels)
        self.show_labels_cb.stateChanged.connect(self.on_settings_changed)
        display_layout.addWidget(self.show_labels_cb)

        self.show_dimensions_cb = QCheckBox("Показывать размеры")
        self.show_dimensions_cb.setChecked(self.settings.show_dimensions)
        self.show_dimensions_cb.stateChanged.connect(self.on_settings_changed)
        display_layout.addWidget(self.show_dimensions_cb)

        layout.addWidget(display_group)

        # Группа статистики рулона
        self.stats_group = QGroupBox("Статистика рулона")
        self.stats_layout = QVBoxLayout(self.stats_group)
        self.stats_label = QLabel("Нет данных")
        self.stats_layout.addWidget(self.stats_label)
        layout.addWidget(self.stats_group)

        # Группа легенды
        legend_group = QGroupBox("Легенда")
        legend_layout = QVBoxLayout(legend_group)

        # Синий прямоугольник для деталей
        legend_layout.addWidget(self.create_legend_item("Детали", QColor(100, 150, 255)))
        # Зеленый прямоугольник для остатков
        legend_layout.addWidget(self.create_legend_item("Деловые остатки", QColor(150, 255, 150)))
        # Красный прямоугольник для отходов
        legend_layout.addWidget(self.create_legend_item("Отходы", QColor(255, 100, 100)))

        layout.addWidget(legend_group)

        layout.addStretch()

        return panel

    def create_legend_item(self, text: str, color: QColor) -> QWidget:
        """Создание элемента легенды"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 2, 5, 2)

        # Цветной квадратик
        color_label = QLabel()
        color_label.setFixedSize(20, 20)
        color_label.setStyleSheet(f"background-color: {color.name()}; border: 1px solid black;")
        layout.addWidget(color_label)

        # Текст
        text_label = QLabel(text)
        layout.addWidget(text_label)

        layout.addStretch()
        return widget

    def set_optimization_result(self, result: FiberglassOptimizationResult):
        """Установить результат оптимизации для визуализации"""
        print(f"🔧 DEBUG: set_optimization_result вызван с result={result}")
        self.optimization_result = result

        # Обновляем список рулонов
        self.roll_combo.clear()
        if result and hasattr(result, 'layouts') and result.layouts:
            print(f"🔧 DEBUG: Найдено {len(result.layouts)} рулонов")
            for i, layout in enumerate(result.layouts):
                roll_info = f"Рулон {i+1}: {layout.sheet.width:.0f}×{layout.sheet.height:.0f}мм"
                self.roll_combo.addItem(roll_info)
                print(f"🔧 DEBUG: Добавлен рулон {i+1}: {roll_info}")
            self.roll_combo.setCurrentIndex(0)
            self.update_visualization()
        else:
            # Очищаем визуализацию если результатов нет
            print(f"🔧 DEBUG: Результатов нет или layouts пустые. result={result}")
            if result:
                print(f"🔧 DEBUG: result.layouts = {getattr(result, 'layouts', 'NO ATTR')}")
            self.canvas.set_layout(None)
            self.roll_combo.addItem("Нет данных для визуализации")
            self.update_stats(None)

    def clear_visualization(self):
        """Очистить визуализацию"""
        self.optimization_result = None
        self.roll_combo.clear()
        self.roll_combo.addItem("Ожидание результатов оптимизации...")
        self.canvas.set_layout(None)
        self.update_stats(None)

    def on_roll_changed(self, index: int):
        """Обработчик изменения выбранного рулона"""
        if index >= 0 and self.optimization_result and self.optimization_result.layouts:
            self.current_roll_index = index
            self.update_visualization()

    def update_visualization(self):
        """Обновление визуализации"""
        if not self.optimization_result or not self.optimization_result.layouts:
            return

        current_layout = self.optimization_result.layouts[self.current_roll_index]
        self.canvas.set_layout(current_layout)

        # Обновляем статистику
        self.update_stats(current_layout)

    def update_stats(self, layout: FiberglassRollLayout):
        """Обновление статистики рулона"""
        if not layout or not hasattr(layout, 'sheet'):
            self.stats_label.setText("Нет данных для отображения статистики")
            return

        total_area = layout.sheet.width * layout.sheet.height
        used_area = sum(item.area for item in layout.placed_items if item.item_type == 'detail')
        waste_area = sum(item.area for item in layout.placed_items if item.item_type == 'waste')
        remainder_area = sum(item.area for item in layout.placed_items if item.item_type == 'remainder')

        efficiency = (used_area + remainder_area) / total_area * 100 if total_area > 0 else 0
        waste_percent = waste_area / total_area * 100 if total_area > 0 else 0

        stats_text = ".0f"".0f"".0f"".0f"".1f"".1f"

        self.stats_label.setText(stats_text)

    def zoom_in(self):
        """Увеличить масштаб"""
        self.settings.scale = min(self.settings.scale * 1.2, 5.0)
        self.canvas.set_settings(self.settings)

    def zoom_out(self):
        """Уменьшить масштаб"""
        self.settings.scale = max(self.settings.scale / 1.2, 0.1)
        self.canvas.set_settings(self.settings)

    def fit_to_view(self):
        """Вписать раскладку в область просмотра"""
        if not self.optimization_result or not self.optimization_result.layouts:
            return

        current_layout = self.optimization_result.layouts[self.current_roll_index]
        roll_width = current_layout.sheet.width
        roll_height = current_layout.sheet.height

        # Вычисляем масштаб для вписывания
        canvas_width = self.canvas.width() - 2 * self.settings.margin
        canvas_height = self.canvas.height() - 2 * self.settings.margin

        scale_x = canvas_width / roll_width if roll_width > 0 else 1.0
        scale_y = canvas_height / roll_height if roll_height > 0 else 1.0

        self.settings.scale = min(scale_x, scale_y, 1.0)  # Не увеличиваем больше 1:1
        self.canvas.set_settings(self.settings)

    def on_settings_changed(self):
        """Обработчик изменения настроек"""
        self.settings.show_grid = self.show_grid_cb.isChecked()
        self.settings.show_labels = self.show_labels_cb.isChecked()
        self.settings.show_dimensions = self.show_dimensions_cb.isChecked()
        self.canvas.set_settings(self.settings)
