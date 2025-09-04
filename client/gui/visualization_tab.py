#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Вкладка визуализации 2D раскроя фибергласса
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QComboBox,
    QScrollArea, QFrame, QSplitter, QGroupBox,
    QSlider, QCheckBox, QToolBar,
    QToolButton, QMenu, QShortcut,
    QGraphicsTextItem, QTableWidget
)
from PyQt5.QtCore import Qt, QPointF, pyqtSignal
from PyQt5.QtGui import QPainter, QPen, QBrush, QColor, QFont, QPixmap
from typing import List, Optional
from dataclasses import dataclass
from collections import Counter

from core.models import FiberglassOptimizationResult, FiberglassRollLayout, PlacedFiberglassItem
from gui.table_widgets import setup_table_columns, _create_numeric_item, _create_text_item


@dataclass
class VisualizationSettings:
    """Настройки визуализации"""
    scale: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0
    show_grid: bool = True
    show_labels: bool = True
    show_dimensions: bool = True  # Размеры по умолчанию включены
    show_minimap: bool = True
    grid_size: int = 50  # Размер сетки в пикселях
    margin: int = 20    # Отступы от краев
    roll_spacing: int = 50  # Расстояние между рулонами
    highlight_on_hover: bool = True
    show_tooltips: bool = True
    smooth_zoom: bool = True
    zoom_step: float = 1.2  # Коэффициент зума
    min_zoom: float = 0.1
    max_zoom: float = 5.0


class FiberglassCanvas(QFrame):
    """Холст для отрисовки раскладки фибергласса с поддержкой интерактивности"""

    # Сигналы для коммуникации с родительскими виджетами
    zoom_changed = pyqtSignal(float)  # scale: float
    pan_changed = pyqtSignal(float, float)  # offset_x, offset_y
    item_hovered = pyqtSignal(object)  # hovered_item

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(800, 600)
        self.setFrameStyle(QFrame.Box)

        # Включаем прием событий мыши и колесика
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        # Данные для отрисовки
        self.layout: Optional[FiberglassRollLayout] = None
        self.settings = VisualizationSettings()

        # Состояние мыши и интерактивности
        self.is_dragging = False
        self.last_mouse_pos = QPointF()
        self.hovered_item: Optional[PlacedFiberglassItem] = None
        self.selected_items: List[PlacedFiberglassItem] = []

        # Цвета для разных типов элементов (черно-белая схема)
        self.colors = {
            'detail': QColor(200, 200, 200),      # Светло-серый для деталей
            'remainder': QColor(150, 150, 150),   # Средне-серый для деловых остатков
            'waste': QColor(100, 100, 100),       # Темно-серый для отходов
            'background': QColor(240, 240, 240),  # Фон
            'grid': QColor(100, 100, 100, 150),   # Темная сетка с прозрачностью
            'text': QColor(50, 50, 50),           # Текст
            'roll_border': QColor(0, 0, 0),       # Граница рулона
            'highlight': QColor(255, 255, 0, 100), # Подсветка при наведении (желтая)
            'selection': QColor(255, 215, 0, 150), # Выделение (золотистое)
            'minimap_bg': QColor(245, 245, 245), # Фон мини-карты
            'minimap_border': QColor(150, 150, 150), # Граница мини-карты
            'minimap_viewport': QColor(100, 100, 255, 100) # Область просмотра на мини-карте (синяя)
        }

        # Шрифты
        self.fonts = {
            'label': QFont('Arial', 8),
            'dimension': QFont('Arial', 7),
            'tooltip': QFont('Arial', 9, QFont.Bold)
        }

        # Кэш для производительности
        self._cached_pixmap: Optional[QPixmap] = None
        self._cache_valid = False

    def set_layout(self, layout: FiberglassRollLayout):
        """Установить раскладку для отрисовки"""
        self.layout = layout
        self._cache_valid = False
        self.update()

    def set_settings(self, settings: VisualizationSettings):
        """Установить настройки визуализации"""
        self.settings = settings
        self._cache_valid = False
        self.update()

    def wheelEvent(self, event):
        """Обработка колесика мыши для зума"""
        if not self.layout:
            return

        # Определяем центр зума (позиция курсора)
        center_pos = event.pos()

        # Вычисляем коэффициент зума
        zoom_factor = self.settings.zoom_step if event.angleDelta().y() > 0 else 1.0 / self.settings.zoom_step

        # Ограничиваем масштаб
        new_scale = self.settings.scale * zoom_factor
        new_scale = max(self.settings.min_zoom, min(self.settings.max_zoom, new_scale))

        if abs(new_scale - self.settings.scale) < 0.01:
            return  # Масштаб не изменился существенно

        # Вычисляем смещение, чтобы зум был относительно курсора

        # Преобразуем позицию курсора в координаты раскладки
        layout_x = (center_pos.x() - self.settings.offset_x) / self.settings.scale
        layout_y = (center_pos.y() - self.settings.offset_y) / self.settings.scale

        # Обновляем масштаб и смещение
        self.settings.scale = new_scale
        self.settings.offset_x = center_pos.x() - layout_x * new_scale
        self.settings.offset_y = center_pos.y() - layout_y * new_scale

        self._cache_valid = False
        self.update()

        # Отправляем сигнал об изменении масштаба
        self.zoom_changed.emit(self.settings.scale)

    def mousePressEvent(self, event):
        """Обработка нажатия кнопки мыши"""
        if event.button() == Qt.LeftButton:
            self.is_dragging = True
            self.last_mouse_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)

            # Проверяем, нажали ли на элемент
            if self.layout and self.settings.highlight_on_hover:
                clicked_item = self._get_item_at_position(event.pos())
                if clicked_item:
                    if event.modifiers() & Qt.ControlModifier:
                        # Ctrl+клик - добавление/удаление из выделения
                        if clicked_item in self.selected_items:
                            self.selected_items.remove(clicked_item)
                        else:
                            self.selected_items.append(clicked_item)
                    else:
                        # Обычный клик - новое выделение
                        self.selected_items = [clicked_item]
                    self._cache_valid = False
                    self.update()

        elif event.button() == Qt.RightButton:
            # Правая кнопка - контекстное меню
            self._show_context_menu(event.pos())

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Обработка движения мыши"""
        if self.is_dragging and self.layout:
            # Перетаскивание холста
            delta = event.pos() - self.last_mouse_pos
            self.settings.offset_x += delta.x()
            self.settings.offset_y += delta.y()
            self.last_mouse_pos = event.pos()
            self._cache_valid = False
            self.update()

            # Отправляем сигнал об изменении позиции
            self.pan_changed.emit(self.settings.offset_x, self.settings.offset_y)
        else:
            # Обновляем hovered элемент
            if self.layout and self.settings.highlight_on_hover:
                new_hovered = self._get_item_at_position(event.pos())
                if new_hovered != self.hovered_item:
                    self.hovered_item = new_hovered
                    self._cache_valid = False
                    self.update()

                    # Отправляем сигнал о наведении
                    self.item_hovered.emit(new_hovered)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Обработка отпускания кнопки мыши"""
        if event.button() == Qt.LeftButton:
            self.is_dragging = False
            self.setCursor(Qt.ArrowCursor)

        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        """Обработка нажатий клавиш"""
        if event.key() == Qt.Key_Escape:
            # Сброс выделения
            self.selected_items.clear()
            self._cache_valid = False
            self.update()
        elif event.key() == Qt.Key_Delete:
            # Удаление выделенных элементов (если поддерживается)
            pass

        super().keyPressEvent(event)

    def _get_item_at_position(self, pos: QPointF) -> Optional[PlacedFiberglassItem]:
        """Определить элемент под указанной позицией"""
        if not self.layout:
            return None

        # Преобразуем позицию курсора в координаты раскладки
        layout_x = (pos.x() - self.settings.offset_x) / self.settings.scale
        layout_y = (pos.y() - self.settings.offset_y) / self.settings.scale

        # Проверяем все элементы
        for item in self.layout.placed_items:
            if (item.x <= layout_x <= item.x + item.width and
                item.y <= layout_y <= item.y + item.height):
                return item

        return None

    def _show_context_menu(self, pos):
        """Показать контекстное меню"""
        menu = QMenu(self)

        # Действия для выделенных элементов
        if self.selected_items:
            copy_action = menu.addAction("📋 Копировать информацию")
            copy_action.triggered.connect(lambda: self._copy_item_info())

            menu.addSeparator()

            clear_selection_action = menu.addAction("❌ Снять выделение")
            clear_selection_action.triggered.connect(lambda: self._clear_selection())

        menu.addSeparator()

        # Общие действия
        zoom_in_action = menu.addAction("🔍 Увеличить")
        zoom_in_action.triggered.connect(self.zoom_in)

        zoom_out_action = menu.addAction("🔍 Уменьшить")
        zoom_out_action.triggered.connect(self.zoom_out)

        fit_action = menu.addAction("📐 Вписать в окно")
        fit_action.triggered.connect(self.fit_to_view)

        menu.addSeparator()

        export_action = menu.addAction("💾 Экспорт изображения...")
        export_action.triggered.connect(self.export_image)

        menu.exec_(self.mapToGlobal(pos))

    def _copy_item_info(self):
        """Копировать информацию о выделенных элементах"""
        if not self.selected_items:
            return

        info_lines = []
        for item in self.selected_items:
            if item.item_type == 'detail' and item.detail:
                info_lines.append(f"Деталь: {item.detail.marking}")
                info_lines.append(f"Размеры: {item.width}×{item.height}мм")
                info_lines.append(f"Позиция: ({item.x}, {item.y})")
                info_lines.append(f"Поворот: {'Да' if item.is_rotated else 'Нет'}")
            elif item.item_type == 'remainder':
                info_lines.append(f"Деловой остаток: {item.width}×{item.height}мм")
                info_lines.append(f"Позиция: ({item.x}, {item.y})")
            else:
                info_lines.append(f"Отход: {item.width}×{item.height}мм")
                info_lines.append(f"Позиция: ({item.x}, {item.y})")
            info_lines.append("")

        # Копируем в буфер обмена
        from PyQt5.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText("\n".join(info_lines))

    def _clear_selection(self):
        """Снять выделение"""
        self.selected_items.clear()
        self._cache_valid = False
        self.update()

    def zoom_in(self):
        """Увеличить масштаб (для контекстного меню)"""
        center_pos = QPointF(self.width() / 2, self.height() / 2)
        self._zoom_at_point(center_pos, self.settings.zoom_step)

    def zoom_out(self):
        """Уменьшить масштаб (для контекстного меню)"""
        center_pos = QPointF(self.width() / 2, self.height() / 2)
        self._zoom_at_point(center_pos, 1.0 / self.settings.zoom_step)

    def fit_to_view(self):
        """Вписать раскладку в область просмотра"""
        if not self.layout:
            return

        roll_width = self.layout.sheet.width
        roll_height = self.layout.sheet.height

        # Вычисляем масштаб для вписывания
        canvas_width = self.width() - 2 * self.settings.margin
        canvas_height = self.height() - 2 * self.settings.margin

        scale_x = canvas_width / roll_width if roll_width > 0 else 1.0
        scale_y = canvas_height / roll_height if roll_height > 0 else 1.0

        self.settings.scale = min(scale_x, scale_y, 1.0)
        self.settings.offset_x = (self.width() - roll_width * self.settings.scale) / 2
        self.settings.offset_y = (self.height() - roll_height * self.settings.scale) / 2

        self._cache_valid = False
        self.update()

    def _zoom_at_point(self, center_pos: QPointF, zoom_factor: float):
        """Зум относительно указанной точки"""
        if not self.layout:
            return

        # Ограничиваем масштаб
        new_scale = self.settings.scale * zoom_factor
        new_scale = max(self.settings.min_zoom, min(self.settings.max_zoom, new_scale))

        if abs(new_scale - self.settings.scale) < 0.01:
            return

        # Преобразуем позицию в координаты раскладки
        layout_x = (center_pos.x() - self.settings.offset_x) / self.settings.scale
        layout_y = (center_pos.y() - self.settings.offset_y) / self.settings.scale

        # Обновляем масштаб и смещение
        self.settings.scale = new_scale
        self.settings.offset_x = center_pos.x() - layout_x * new_scale
        self.settings.offset_y = center_pos.y() - layout_y * new_scale

        self._cache_valid = False
        self.update()

    def export_image(self):
        """Экспорт изображения раскладки с расширенными форматами"""
        if not self.layout:
            return

        from PyQt5.QtWidgets import QFileDialog
        filename, selected_filter = QFileDialog.getSaveFileName(
            self, "Экспорт изображения", "",
            "PNG файлы (*.png);;JPEG файлы (*.jpg);;BMP файлы (*.bmp);;PDF файлы (*.pdf)"
        )

        if not filename:
            return

        # Определяем формат по расширению файла
        if filename.lower().endswith('.pdf'):
            self._export_to_pdf(filename)
        else:
            self._export_to_image(filename)

    def _export_to_image(self, filename):
        """Экспорт в растровые форматы"""
        # Создаем изображение нужного размера
        roll_width = int(self.layout.sheet.width * self.settings.scale)
        roll_height = int(self.layout.sheet.height * self.settings.scale)

        pixmap = QPixmap(roll_width + 2 * self.settings.margin,
                       roll_height + 2 * self.settings.margin)
        pixmap.fill(self.colors['background'])

        # Отрисовываем раскладку
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Временные настройки для экспорта (без смещения)
        temp_settings = self.settings
        temp_settings.offset_x = self.settings.margin
        temp_settings.offset_y = self.settings.margin

        self._draw_roll_border(painter, temp_settings.offset_x, temp_settings.offset_y,
                             roll_width, roll_height)

        for item in self.layout.placed_items:
            self._draw_item(painter, item, temp_settings.offset_x, temp_settings.offset_y,
                          temp_settings.scale)

        painter.end()

        # Сохраняем изображение
        if not pixmap.save(filename):
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Ошибка экспорта", "Не удалось сохранить изображение")

    def _export_to_pdf(self, filename):
        """Экспорт в PDF формат"""
        try:
            from PyQt5.QtGui import QPdfWriter, QPainter
            from PyQt5.QtCore import QRectF

            # Создаем PDF writer
            pdf_writer = QPdfWriter(filename)
            pdf_writer.setPageSize(QPdfWriter.A4)
            pdf_writer.setResolution(300)  # Высокое разрешение

            # Вычисляем размеры для PDF
            roll_width = self.layout.sheet.width
            roll_height = self.layout.sheet.height

            # Масштабируем для A4 (предполагаем альбомную ориентацию)
            page_width = 210  # мм (A4 ширина)
            page_height = 297  # мм (A4 высота)

            # Вычисляем масштаб для вписывания
            scale_x = (page_width - 20) / roll_width  # с отступами
            scale_y = (page_height - 20) / roll_height
            pdf_scale = min(scale_x, scale_y, 1.0)

            painter = QPainter(pdf_writer)
            painter.setRenderHint(QPainter.Antialiasing)

            # Устанавливаем масштаб и смещение для PDF
            pdf_margin = 10  # мм
            pdf_offset_x = pdf_margin
            pdf_offset_y = pdf_margin

            # Рисуем границы рулона
            painter.setPen(QPen(self.colors['roll_border'], 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(int(pdf_offset_x), int(pdf_offset_y),
                           int(roll_width * pdf_scale), int(roll_height * pdf_scale))

            # Рисуем элементы
            for item in self.layout.placed_items:
                item_x = pdf_offset_x + item.x * pdf_scale
                item_y = pdf_offset_y + item.y * pdf_scale
                item_width = item.width * pdf_scale
                item_height = item.height * pdf_scale

                # Выбираем цвет (черно-белая схема, все элементы без заливки)
                if item.item_type == 'detail':
                    color = QColor(255, 255, 255, 0)  # Прозрачная заливка для деталей
                    border_color = QColor(100, 100, 100)  # Темно-серый для деталей
                elif item.item_type == 'remainder':
                    color = QColor(255, 255, 255, 0)  # Прозрачная заливка для остатков
                    border_color = QColor(80, 80, 80)    # Средне-темно-серый для остатков
                else:
                    color = QColor(255, 255, 255, 0)     # Прозрачная заливка для отходов
                    border_color = QColor(50, 50, 50)     # Очень темный серый для отходов

                painter.setPen(QPen(border_color, 0.5))
                painter.setBrush(QBrush(color))
                painter.drawRect(int(item_x), int(item_y), int(item_width), int(item_height))

            painter.end()

        except Exception as e:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Ошибка экспорта PDF", f"Не удалось создать PDF файл:\n{str(e)}")

    def paintEvent(self, event):
        """Отрисовка раскладки с поддержкой кэширования"""
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

        # Используем смещение из настроек вместо центрирования
        offset_x = self.settings.offset_x
        offset_y = self.settings.offset_y

        # Масштабируем размеры
        scaled_width = roll_width * self.settings.scale
        scaled_height = roll_height * self.settings.scale

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

        # Рисуем мини-карту если включена
        if self.settings.show_minimap:
            self._draw_minimap(painter)

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
        # Сохраняем текущее состояние рисования
        painter.save()

        # Устанавливаем цвет и стиль сетки
        painter.setPen(QPen(self.colors['grid'], 1, Qt.DotLine))
        painter.setOpacity(0.6)  # Дополнительная прозрачность

        # Вычисляем размер сетки с учетом масштаба (делаем сетку плотнее при увеличении)
        scaled_grid_size = max(20, self.settings.grid_size / max(0.1, self.settings.scale))

        # Вертикальные линии
        x = offset_x
        while x <= offset_x + width:
            painter.drawLine(int(x), int(offset_y), int(x), int(offset_y + height))
            x += scaled_grid_size

        # Горизонтальные линии
        y = offset_y
        while y <= offset_y + height:
            painter.drawLine(int(offset_x), int(y), int(offset_x + width), int(y))
            y += scaled_grid_size

        # Восстанавливаем состояние рисования
        painter.restore()

    def _draw_roll_border(self, painter: QPainter, offset_x: float, offset_y: float,
                         width: float, height: float):
        """Отрисовка границы рулона"""
        painter.setPen(QPen(self.colors['roll_border'], 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(int(offset_x), int(offset_y), int(width), int(height))

    def _draw_item(self, painter: QPainter, item: PlacedFiberglassItem,
                   offset_x: float, offset_y: float, scale: float):
        """Отрисовка размещенного элемента с поддержкой подсветки и выделения"""
        # Вычисляем координаты с учетом масштаба
        x = offset_x + item.x * scale
        y = offset_y + item.y * scale
        width = item.width * scale
        height = item.height * scale

        # Выбираем цвет в зависимости от типа (черно-белая схема, все элементы без заливки)
        if item.item_type == 'detail':
            color = QColor(255, 255, 255, 0)  # Прозрачная заливка для деталей
            border_color = QColor(100, 100, 100)  # Темно-серый для деталей
        elif item.item_type == 'remainder':
            color = QColor(255, 255, 255, 0)  # Прозрачная заливка для остатков
            border_color = QColor(80, 80, 80)    # Средне-темно-серый для остатков
        else:  # waste
            color = QColor(255, 255, 255, 0)     # Прозрачная заливка для отходов
            border_color = QColor(50, 50, 50)     # Очень темный серый для отходов

        # Проверяем, нужно ли рисовать подсветку или выделение
        is_highlighted = (self.settings.highlight_on_hover and item == self.hovered_item)
        is_selected = item in self.selected_items

        # Рисуем подсветку/выделение
        if is_highlighted or is_selected:
            highlight_color = self.colors['selection'] if is_selected else self.colors['highlight']
            painter.setPen(QPen(highlight_color, 3))
            painter.setBrush(QBrush(highlight_color))
            painter.drawRect(int(x - 2), int(y - 2), int(width + 4), int(height + 4))

        # Рисуем основной прямоугольник
        painter.setPen(QPen(border_color, 2 if is_selected else 1))
        painter.setBrush(QBrush(color))
        painter.drawRect(int(x), int(y), int(width), int(height))

        # Рисуем метку всегда для всех элементов
        if self.settings.show_labels:
            self._draw_item_label(painter, item, x, y, width, height)

        # Рисуем размеры если включено (ПОКА ОТКЛЮЧЕНО)
        # if self.settings.show_dimensions:
        #     self._draw_item_dimensions(painter, item, x, y, width, height)

    def _draw_item_label(self, painter: QPainter, item: PlacedFiberglassItem,
                        x: float, y: float, width: float, height: float):
        """Отрисовка метки элемента с полной информацией в 3 строки"""
        # Определяем текст для отображения
        text_parts = []

        if item.item_type == 'detail' and item.detail:
            # 1) Номер заказа
            if hasattr(item.detail, 'orderno') and item.detail.orderno:
                text_parts.append(str(item.detail.orderno))
            
            # 2) Номер изделия + / + номер части изделия
            line2_parts = []
            if hasattr(item.detail, 'item_name') and item.detail.item_name:
                line2_parts.append(str(item.detail.item_name))
            if hasattr(item.detail, 'izdpart') and item.detail.izdpart:
                line2_parts.append(str(item.detail.izdpart))
            
            if line2_parts:
                text_parts.append("/".join(line2_parts))
            
            # 3) Размеры
            text_parts.append(f"{item.width:.0f}×{item.height:.0f}")

            # Признак поворота добавляем к размерам
            if item.is_rotated:
                text_parts[-1] += " ↻"

        elif item.item_type == 'remainder':
            # Всегда показываем размеры остатков
            text_parts.append("ОСТ")
            text_parts.append(f"{item.width:.0f}×{item.height:.0f}")

        elif item.item_type == 'waste':
            # Всегда показываем размеры отходов
            text_parts.append("ОТХ")
            text_parts.append(f"{item.width:.0f}×{item.height:.0f}")

        if text_parts:
            # Вычисляем адаптивный размер шрифта с учетом масштаба
            # Для многострочного текста используем объединенный текст для расчета размера
            full_text_for_size = "\n".join(text_parts)
            font_size = _calculate_adaptive_font_size_with_scale(full_text_for_size, width, height, self.settings.scale)

            if font_size >= 6:  # Рисуем текст если шрифт >= 6pt (минимальный читаемый размер)
                # Выбираем цвет текста в зависимости от типа элемента (все элементы без заливки)
                if item.item_type == 'detail':
                    painter.setPen(QPen(QColor(0, 0, 0)))        # Черный текст на прозрачном фоне
                elif item.item_type == 'remainder':
                    painter.setPen(QPen(QColor(0, 0, 0)))        # Черный текст на прозрачном фоне
                else:  # waste
                    painter.setPen(QPen(QColor(0, 0, 0)))        # Черный текст на прозрачном фоне

                painter.setFont(QFont("Arial", font_size, QFont.Weight.Bold))
                
                # Получаем метрики шрифта для расчета высоты строки
                font_metrics = painter.fontMetrics()
                line_height = font_metrics.height()
                
                # Вычисляем общую высоту текста
                total_text_height = len(text_parts) * line_height
                
                # Определяем ориентацию текста в зависимости от формы элемента
                if width > height:
                    # Горизонтально вытянутый элемент - текст горизонтально
                    # Начальная позиция Y (центрируем весь блок текста)
                    start_y = y + (height - total_text_height) / 2 + line_height
                    
                    # Рисуем каждую строку отдельно
                    for i, line in enumerate(text_parts):
                        if line.strip():  # Пропускаем пустые строки
                            line_width = font_metrics.width(line)
                            text_x = x + (width - line_width) / 2  # Центрируем каждую строку
                            text_y = start_y + i * line_height
                            painter.drawText(int(text_x), int(text_y), line)
                else:
                    # Вертикально вытянутый элемент - поворачиваем текст на 90 градусов
                    painter.save()
                    painter.translate(x + width / 2, y + height / 2)
                    painter.rotate(-90)
                    
                    # Начальная позиция Y для повернутого текста (центрируем весь блок)
                    start_y = -(total_text_height / 2) + line_height
                    
                    # Рисуем каждую строку отдельно
                    for i, line in enumerate(text_parts):
                        if line.strip():  # Пропускаем пустые строки
                            line_width = font_metrics.width(line)
                            text_x = -line_width / 2  # Центрируем каждую строку
                            text_y = start_y + i * line_height
                            painter.drawText(int(text_x), int(text_y), line)
                    
                    painter.restore()

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
        if not self.layout:
            return

        painter.setPen(QPen(self.colors['text']))
        painter.setFont(QFont('Arial', 10, QFont.Bold))

        # Показываем размеры рулона
        info_text = f"Рулон: {self.layout.sheet.width:.0f}×{self.layout.sheet.height:.0f}мм"
        painter.drawText(int(offset_x), int(offset_y - 5), info_text)

    def _draw_minimap(self, painter: QPainter):
        """Отрисовка мини-карты"""
        if not self.layout:
            return

        # Размеры мини-карты
        minimap_size = 150
        minimap_margin = 10
        minimap_x = self.width() - minimap_size - minimap_margin
        minimap_y = minimap_margin

        # Рисуем фон мини-карты
        painter.setPen(QPen(self.colors['minimap_border'], 1))
        painter.setBrush(QBrush(self.colors['minimap_bg']))
        painter.drawRect(minimap_x, minimap_y, minimap_size, minimap_size)

        # Вычисляем масштаб мини-карты
        roll_width = self.layout.sheet.width
        roll_height = self.layout.sheet.height
        max_roll_size = max(roll_width, roll_height)

        if max_roll_size > 0:
            minimap_scale = (minimap_size - 10) / max_roll_size
            minimap_roll_width = roll_width * minimap_scale
            minimap_roll_height = roll_height * minimap_scale

            # Центрируем рулон на мини-карте
            minimap_roll_x = minimap_x + (minimap_size - minimap_roll_width) / 2
            minimap_roll_y = minimap_y + (minimap_size - minimap_roll_height) / 2

            # Рисуем рулон на мини-карте
            painter.setPen(QPen(self.colors['roll_border'], 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(int(minimap_roll_x), int(minimap_roll_y),
                           int(minimap_roll_width), int(minimap_roll_height))

            # Рисуем элементы на мини-карте
            for item in self.layout.placed_items:
                item_x = minimap_roll_x + item.x * minimap_scale
                item_y = minimap_roll_y + item.y * minimap_scale
                item_width = item.width * minimap_scale
                item_height = item.height * minimap_scale

                # Выбираем цвет для мини-карты
                if item.item_type == 'detail':
                    color = self.colors['detail']
                elif item.item_type == 'remainder':
                    color = self.colors['remainder']
                else:
                    color = self.colors['waste']

                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(color))
                painter.drawRect(int(item_x), int(item_y), max(1, int(item_width)), max(1, int(item_height)))

            # Рисуем область просмотра
            if self.layout:
                # Вычисляем область просмотра на мини-карте
                view_left = minimap_roll_x - (self.settings.offset_x - minimap_roll_x) / self.settings.scale * minimap_scale
                view_top = minimap_roll_y - (self.settings.offset_y - minimap_roll_y) / self.settings.scale * minimap_scale
                view_width = self.width() / self.settings.scale * minimap_scale
                view_height = self.height() / self.settings.scale * minimap_scale

                painter.setPen(QPen(self.colors['minimap_viewport'], 2))
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(int(view_left), int(view_top), int(view_width), int(view_height))


def _calculate_adaptive_font_size_with_scale(text, rect_width, rect_height, scale):
    """
    Вычисляет оптимальный размер шрифта для текста в прямоугольнике с учетом масштаба
    Улучшенная версия для обеспечения видимости на всех масштабах

    Args:
        text: текст для отображения
        rect_width: ширина прямоугольника в пикселях
        rect_height: высота прямоугольника в пикселях
        scale: текущий масштаб визуализации

    Returns:
        int: размер шрифта (минимальный 6pt)
    """
    # Учитываем масштаб - при отдалении увеличиваем базовый размер шрифта
    scale_factor = max(1.0, 2.0 / scale)  # При отдалении (scale < 1) увеличиваем шрифт

    min_dimension = min(rect_width, rect_height)

    # Базовые размеры с учетом масштаба
    if min_dimension > 400:
        base_font_size = int(28 * scale_factor)
    elif min_dimension > 200:
        base_font_size = int(24 * scale_factor)
    elif min_dimension > 100:
        base_font_size = int(20 * scale_factor)
    elif min_dimension > 50:
        base_font_size = int(16 * scale_factor)
    else:
        base_font_size = int(12 * scale_factor)

    # Ограничиваем максимальный размер шрифта
    base_font_size = min(base_font_size, 36)

    # Минимальный размер шрифта для читаемости
    min_font_size = 6

    # Пробуем размеры от базового до минимального
    for font_size in range(max(base_font_size, min_font_size), min_font_size - 1, -1):
        # Создаем временный элемент для измерения
        temp_item = QGraphicsTextItem(text)
        temp_item.setFont(QFont("Arial", font_size, QFont.Weight.Bold))
        text_rect = temp_item.boundingRect()

        # Меньшие требования для маленьких элементов при сильном отдалении
        if min_dimension < 100 and scale < 0.5:
            margin = 0.9  # 90% заполнения для маленьких элементов при отдалении
        elif min_dimension < 100:
            margin = 0.8  # 80% заполнения для маленьких элементов
        else:
            margin = 0.85  # 85% заполнения для больших элементов

        # Проверяем, помещается ли текст
        if (text_rect.width() <= rect_width * margin and
            text_rect.height() <= rect_height * margin):
            return font_size

    # Если ничего не подошло, все равно возвращаем минимальный размер для читаемости
    return min_font_size


def _calculate_adaptive_font_size(text, rect_width, rect_height):
    """
    Вычисляет оптимальный размер шрифта для текста в прямоугольнике
    Улучшенная версия из Glass Optimizer с увеличенными размерами

    Args:
        text: текст для отображения
        rect_width: ширина прямоугольника
        rect_height: высота прямоугольника

    Returns:
        int: размер шрифта (0 если текст не помещается)
    """
    return _calculate_adaptive_font_size_with_scale(text, rect_width, rect_height, 1.0)


class VisualizationTab(QWidget):
    """Вкладка визуализации раскроя с улучшенным управлением"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.optimization_result: Optional[FiberglassOptimizationResult] = None
        self.current_roll_index = 0
        self.settings = VisualizationSettings()

        self.init_ui()

    def init_ui(self):
        """Инициализация интерфейса с улучшенными элементами управления"""
        layout = QVBoxLayout(self)

        # Панель инструментов
        self.create_toolbar()
        layout.addWidget(self.toolbar)

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

        # Подключаем сигналы холста
        self.canvas.zoom_changed.connect(self._on_zoom_changed)
        self.canvas.pan_changed.connect(self._on_pan_changed)
        self.canvas.item_hovered.connect(self._on_item_hovered)

    def create_toolbar(self):
        """Создание панели инструментов с улучшенными элементами управления"""
        self.toolbar = QToolBar("Визуализация")
        self.toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toolbar.setMovable(False)

        # Выбор рулона
        self.toolbar.addWidget(QLabel("Рулон:"))
        self.roll_combo = QComboBox()
        self.roll_combo.setMinimumWidth(150)
        self.roll_combo.currentIndexChanged.connect(self.on_roll_changed)
        self.toolbar.addWidget(self.roll_combo)

        self.toolbar.addSeparator()

        # Кнопки навигации
        self.fit_btn = QToolButton()
        self.fit_btn.setText("📐")
        self.fit_btn.setToolTip("Вписать в окно (Ctrl+F)")
        self.fit_btn.clicked.connect(self.fit_to_view)
        self.toolbar.addWidget(self.fit_btn)

        self.toolbar.addSeparator()

        # Кнопки масштаба
        self.zoom_out_btn = QToolButton()
        self.zoom_out_btn.setText("🔍-")
        self.zoom_out_btn.setToolTip("Уменьшить (Ctrl+-)")
        self.zoom_out_btn.clicked.connect(self.zoom_out)
        self.toolbar.addWidget(self.zoom_out_btn)

        # Слайдер масштаба
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setMinimum(10)  # 0.1
        self.zoom_slider.setMaximum(500)  # 5.0
        self.zoom_slider.setValue(int(self.settings.scale * 100))
        self.zoom_slider.setMaximumWidth(150)
        self.zoom_slider.setToolTip("Масштаб")
        self.zoom_slider.valueChanged.connect(self._on_zoom_slider_changed)
        self.toolbar.addWidget(self.zoom_slider)

        # Метка текущего масштаба
        self.zoom_label = QLabel(".0%")
        self.zoom_label.setMinimumWidth(60)
        self.toolbar.addWidget(self.zoom_label)

        self.zoom_in_btn = QToolButton()
        self.zoom_in_btn.setText("🔍+")
        self.zoom_in_btn.setToolTip("Увеличить (Ctrl++)")
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.toolbar.addWidget(self.zoom_in_btn)

        self.toolbar.addSeparator()

        # Кнопки экспорта
        self.export_all_pdf_btn = QToolButton()
        self.export_all_pdf_btn.setText("📄")
        self.export_all_pdf_btn.setToolTip("Экспорт всех рулонов в PDF")
        self.export_all_pdf_btn.clicked.connect(self.export_all_to_pdf)
        self.toolbar.addWidget(self.export_all_pdf_btn)

        # Настройка горячих клавиш
        self._setup_shortcuts()

    def _setup_shortcuts(self):
        """Настройка горячих клавиш"""
        from PyQt5.QtGui import QKeySequence

        # Создаем shortcuts для виджета
        shortcuts = [
            ("Ctrl+F", self.fit_to_view),
            ("Ctrl++", self.zoom_in),
            ("Ctrl+=", self.zoom_in),
            ("Ctrl+-", self.zoom_out),
        ]

        for key_seq, callback in shortcuts:
            shortcut = QShortcut(QKeySequence(key_seq), self)
            shortcut.activated.connect(callback)

    def _on_zoom_slider_changed(self, value):
        """Обработчик изменения слайдера масштаба"""
        new_scale = value / 100.0
        if abs(new_scale - self.settings.scale) > 0.01:
            # Центрируем зум относительно центра холста
            center_pos = QPointF(self.canvas.width() / 2, self.canvas.height() / 2)
            self.canvas._zoom_at_point(center_pos, new_scale / self.settings.scale)
            self.update_zoom_display()

    def _on_zoom_changed(self, scale):
        """Обработчик изменения масштаба"""
        self.update_zoom_display()

    def _on_pan_changed(self, offset_x, offset_y):
        """Обработчик изменения позиции"""
        pass

    def _on_item_hovered(self, item):
        """Обработчик наведения на элемент"""
        pass

    def update_zoom_display(self):
        """Обновление отображения текущего масштаба"""
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(int(self.settings.scale * 100))
        self.zoom_slider.blockSignals(False)
        self.zoom_label.setText(f"{self.settings.scale:.0%}")

    def update_status_bar(self):
        """Обновление статусбара с информацией"""
        pass

    def create_left_panel(self):
        """Создание левой панели с настройками, статистикой и таблицами"""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Группа настроек отображения
        display_group = QGroupBox("Настройки отображения")
        display_layout = QVBoxLayout(display_group)

        # Сетка всегда включена
        self.settings.show_grid = True

        self.show_labels_cb = QCheckBox("Показывать метки")
        self.show_labels_cb.setChecked(self.settings.show_labels)
        self.show_labels_cb.stateChanged.connect(self.on_settings_changed)
        display_layout.addWidget(self.show_labels_cb)

        self.show_dimensions_cb = QCheckBox("Показывать размеры")
        self.show_dimensions_cb.setChecked(self.settings.show_dimensions)
        self.show_dimensions_cb.stateChanged.connect(self.on_settings_changed)
        display_layout.addWidget(self.show_dimensions_cb)

        self.show_minimap_cb = QCheckBox("Показывать мини-карту")
        self.show_minimap_cb.setChecked(self.settings.show_minimap)
        self.show_minimap_cb.stateChanged.connect(self.on_settings_changed)
        display_layout.addWidget(self.show_minimap_cb)

        self.highlight_hover_cb = QCheckBox("Подсвечивать при наведении")
        self.highlight_hover_cb.setChecked(self.settings.highlight_on_hover)
        self.highlight_hover_cb.stateChanged.connect(self.on_settings_changed)
        display_layout.addWidget(self.highlight_hover_cb)

        layout.addWidget(display_group)

        # Группа статистики
        stats_group = QGroupBox("Статистика раскроя")
        stats_layout = QVBoxLayout(stats_group)
        self.placed_details_label = QLabel("Размещено деталей: 0 / 0")
        self.waste_area_label = QLabel("Площадь отходов: 0.00 м²")
        self.waste_count_label = QLabel("Количество отходов: 0 шт")
        self.waste_percent_label = QLabel("Процент отходов: 0.0%")
        stats_layout.addWidget(self.placed_details_label)
        stats_layout.addWidget(self.waste_area_label)
        stats_layout.addWidget(self.waste_count_label)
        stats_layout.addWidget(self.waste_percent_label)
        layout.addWidget(stats_group)

        # Таблица деловых остатков
        remnants_group = QGroupBox("Деловые остатки")
        remnants_layout = QVBoxLayout(remnants_group)
        self.remnants_table = QTableWidget()
        setup_table_columns(self.remnants_table, ["Артикул", "Ширина", "Высота", "Кол-во"])
        remnants_layout.addWidget(self.remnants_table)
        layout.addWidget(remnants_group)

        # Таблица отходов
        waste_group = QGroupBox("Отходы")
        waste_layout = QVBoxLayout(waste_group)
        self.waste_table = QTableWidget()
        setup_table_columns(self.waste_table, ["Артикул", "Ширина", "Высота", "Кол-во"])
        waste_layout.addWidget(self.waste_table)
        layout.addWidget(waste_group)


        layout.addStretch()
        return panel

    def set_optimization_result(self, result: FiberglassOptimizationResult):
        """Установить результат оптимизации для визуализации"""
        self.optimization_result = result

        self.roll_combo.clear()
        if result and hasattr(result, 'layouts') and result.layouts:
            for i, layout in enumerate(result.layouts):
                roll_info = f"Рулон {i+1}: {layout.sheet.width:.0f}×{layout.sheet.height:.0f}мм"
                self.roll_combo.addItem(roll_info)
            self.roll_combo.setCurrentIndex(0)
            self.update_visualization()
            self.fit_to_view()
            self.update_statistics_and_tables()
        else:
            self.canvas.set_layout(None)
            self.roll_combo.addItem("Нет данных для визуализации")
            self.update_zoom_display()
            self.clear_statistics_and_tables()

    def clear_visualization(self):
        """Очистить визуализацию"""
        self.optimization_result = None
        self.roll_combo.clear()
        self.roll_combo.addItem("Ожидание результатов оптимизации...")
        self.canvas.set_layout(None)
        self.update_zoom_display()
        self.clear_statistics_and_tables()

    def update_statistics_and_tables(self):
        """Обновление статистики и таблиц с деловыми остатками и отходами"""
        if not self.optimization_result:
            self.clear_statistics_and_tables()
            return

        # Статистика
        total_details = sum(d.quantity for d in self.optimization_result.unplaced_details)
        placed_details = 0
        total_waste_area = 0
        all_remnants = []
        all_waste = []

        for layout in self.optimization_result.layouts:
            placed_details += len([item for item in layout.placed_items if item.item_type == 'detail'])
            total_waste_area += sum(item.area for item in layout.get_waste())
            all_remnants.extend(layout.get_remnants())
            all_waste.extend(layout.get_waste())

        total_details += placed_details
        
        self.placed_details_label.setText(f"Размещено деталей: {placed_details} / {total_details}")
        self.waste_area_label.setText(f"Площадь отходов: {total_waste_area / 1_000_000:.2f} м²")
        self.waste_count_label.setText(f"Количество отходов: {len(all_waste)} шт")
        
        total_sheet_area = sum(layout.sheet.area for layout in self.optimization_result.layouts)
        waste_percent = (total_waste_area / total_sheet_area * 100) if total_sheet_area > 0 else 0
        self.waste_percent_label.setText(f"Процент отходов: {waste_percent:.1f}%")

        # Заполнение таблиц
        self._populate_item_table(self.remnants_table, all_remnants)
        self._populate_item_table(self.waste_table, all_waste)

    def _populate_item_table(self, table: QTableWidget, items: List[PlacedFiberglassItem]):
        """Заполнение таблицы деловыми остатками или отходами."""
        table.setRowCount(0)
        
        # Группируем элементы по размеру и артикулу
        item_counts = Counter((
            item.detail.marking if item.detail else "N/A", 
            int(item.width), 
            int(item.height)
        ) for item in items)

        for (marking, width, height), count in item_counts.items():
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, _create_text_item(marking))
            table.setItem(row, 1, _create_numeric_item(width))
            table.setItem(row, 2, _create_numeric_item(height))
            table.setItem(row, 3, _create_numeric_item(count))
        
        table.resizeColumnsToContents()

    def clear_statistics_and_tables(self):
        """Очистка статистики и таблиц"""
        self.placed_details_label.setText("Размещено деталей: 0 / 0")
        self.waste_area_label.setText("Площадь отходов: 0.00 м²")
        self.waste_count_label.setText("Количество отходов: 0 шт")
        self.waste_percent_label.setText("Процент отходов: 0.0%")
        self.remnants_table.setRowCount(0)
        self.waste_table.setRowCount(0)

    def on_roll_changed(self, index: int):
        """Обработчик изменения выбранного рулона"""
        if index >= 0 and self.optimization_result and self.optimization_result.layouts:
            self.current_roll_index = index
            self.update_visualization()
            self.fit_to_view()  # Автоматически вписываем новый рулон

    def update_visualization(self):
        """Обновление визуализации"""
        if not self.optimization_result or not self.optimization_result.layouts:
            return

        current_layout = self.optimization_result.layouts[self.current_roll_index]
        self.canvas.set_layout(current_layout)

        self.update_zoom_display()

    def zoom_in(self):
        """Увеличить масштаб"""
        center_pos = QPointF(self.canvas.width() / 2, self.canvas.height() / 2)
        self.canvas._zoom_at_point(center_pos, self.settings.zoom_step)

    def zoom_out(self):
        """Уменьшить масштаб"""
        center_pos = QPointF(self.canvas.width() / 2, self.canvas.height() / 2)
        self.canvas._zoom_at_point(center_pos, 1.0 / self.settings.zoom_step)

    def fit_to_view(self):
        """Вписать раскладку в область просмотра"""
        self.canvas.fit_to_view()
        self.update_zoom_display()

    def on_settings_changed(self):
        """Обработчик изменения настроек"""
        # Сетка всегда включена
        self.settings.show_grid = True
        self.settings.show_labels = self.show_labels_cb.isChecked()
        self.settings.show_dimensions = self.show_dimensions_cb.isChecked()
        self.settings.show_minimap = self.show_minimap_cb.isChecked()
        self.settings.highlight_on_hover = self.highlight_hover_cb.isChecked()
        self.canvas.set_settings(self.settings)

    def export_all_to_pdf(self):
        """Экспорт всех рулонов в один PDF-файл с разбивкой по страницам."""
        if not self.optimization_result or not self.optimization_result.layouts:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, "Экспорт в PDF", "Нет данных для экспорта.")
            return

        from PyQt5.QtWidgets import QFileDialog
        filename, _ = QFileDialog.getSaveFileName(
            self, "Экспорт всех рулонов в PDF", "", "PDF файлы (*.pdf)"
        )

        if not filename:
            return

        try:
            from PyQt5.QtGui import QPdfWriter, QPainter, QPen, QFont
            from PyQt5.QtCore import QRectF, Qt

            pdf_writer = QPdfWriter(filename)
            pdf_writer.setPageSize(QPdfWriter.A4)
            pdf_writer.setResolution(300)  # 300 DPI

            painter = QPainter(pdf_writer)
            painter.setRenderHint(QPainter.Antialiasing)

            # Размеры страницы A4 в точках при 300 DPI
            page_width_pts = pdf_writer.width()
            page_height_pts = pdf_writer.height()
            margin_pts = 50  # Отступ в точках

            drawable_width = page_width_pts - 2 * margin_pts
            drawable_height = page_height_pts - 2 * margin_pts
            
            header_font = QFont("Arial", 12)
            item_font = QFont("Arial", 8)
            painter.setFont(header_font)
            header_height = painter.fontMetrics().height() + 20

            is_first_page = True

            for i, layout in enumerate(self.optimization_result.layouts):
                sheet_info = layout.sheet
                roll_width = sheet_info.width
                roll_height = sheet_info.height
                
                # Масштаб, чтобы вписать рулон по ширине страницы
                scale = drawable_width / roll_width if roll_width > 0 else 1.0
                
                y_offset_on_roll = 0  # Смещение по высоте рулона, которое уже нарисовано
                page_num_for_roll = 1

                while y_offset_on_roll < roll_height:
                    if not is_first_page:
                        pdf_writer.newPage()
                    is_first_page = False

                    # -- Рисуем заголовок --
                    painter.setFont(header_font)
                    painter.setPen(Qt.black)
                    header_text = f"Рулон {i+1} ({sheet_info.width} x {sheet_info.height}) - Стр. {page_num_for_roll}"
                    painter.drawText(QRectF(margin_pts, margin_pts, drawable_width, header_height), Qt.AlignCenter, header_text)

                    # -- Рисуем раскладку --
                    
                    # Сохраняем состояние painter'а
                    painter.save()
                    
                    # Смещаем начало координат для рисования рулона
                    painter.translate(margin_pts, margin_pts + header_height)
                    
                    # Определяем, какая часть рулона помещается на этой странице
                    remaining_roll_height = roll_height - y_offset_on_roll
                    drawable_roll_height_on_page = (drawable_height - header_height) / scale
                    
                    height_to_draw_on_roll = min(remaining_roll_height, drawable_roll_height_on_page)
                    
                    # Устанавливаем "окно" просмотра для painter'a, чтобы обрезать все, что вне
                    clip_rect = QRectF(0, 0, drawable_width, height_to_draw_on_roll * scale)
                    painter.setClipRect(clip_rect)

                    # Рисуем рамку видимой части рулона
                    painter.setPen(QPen(Qt.black, 2))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawRect(QRectF(0, 0, roll_width * scale, height_to_draw_on_roll * scale))

                    # Рисуем элементы
                    for item in layout.placed_items:
                        # Проверяем, попадает ли элемент в видимую область по Y
                        if (item.y + item.height > y_offset_on_roll and
                            item.y < y_offset_on_roll + height_to_draw_on_roll):
                            
                            self._draw_pdf_item(painter, item, y_offset_on_roll, scale, item_font)

                    # Восстанавливаем состояние painter'а
                    painter.restore()

                    y_offset_on_roll += height_to_draw_on_roll
                    page_num_for_roll += 1

            painter.end()
            
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, "Экспорт в PDF", f"Все рулоны успешно экспортированы в {filename}")

        except Exception as e:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Ошибка экспорта PDF", f"Не удалось создать PDF файл:\n{str(e)}")


    def _draw_pdf_item(self, painter, item, y_offset_on_roll, scale, font):
        """Вспомогательная функция для отрисовки одного элемента в PDF."""
        from PyQt5.QtGui import QPen
        from PyQt5.QtCore import QRectF, Qt

        # Координаты элемента относительно видимой части рулона
        item_x_on_page = item.x * scale
        item_y_on_page = (item.y - y_offset_on_roll) * scale
        item_width_scaled = item.width * scale
        item_height_scaled = item.height * scale
        
        rect = QRectF(item_x_on_page, item_y_on_page, item_width_scaled, item_height_scaled)

        # Настройка кисти и пера
        if item.item_type == 'detail':
            border_color = QColor(100, 100, 100)
        elif item.item_type == 'remainder':
            border_color = QColor(80, 80, 80)
        else: # waste
            border_color = QColor(50, 50, 50)
        
        painter.setPen(QPen(border_color, 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect)

        # -- Рисуем текст --
        text_parts = []
        if item.item_type == 'detail' and item.detail:
            if hasattr(item.detail, 'orderno') and item.detail.orderno:
                text_parts.append(str(item.detail.orderno))
            
            line2_parts = []
            if hasattr(item.detail, 'item_name') and item.detail.item_name:
                line2_parts.append(str(item.detail.item_name))
            if hasattr(item.detail, 'izdpart') and item.detail.izdpart:
                line2_parts.append(str(item.detail.izdpart))
            if line2_parts:
                text_parts.append("/".join(line2_parts))
            
            text_parts.append(f"{item.width:.0f}×{item.height:.0f}")
            if item.is_rotated:
                text_parts[-1] += " ↻"
        elif item.item_type == 'remainder':
            text_parts.append("ОСТ")
            text_parts.append(f"{item.width:.0f}×{item.height:.0f}")
        elif item.item_type == 'waste':
            text_parts.append("ОТХ")
            text_parts.append(f"{item.width:.0f}×{item.height:.0f}")

        if text_parts:
            painter.setPen(Qt.black)
            painter.setFont(font)
            # Простое центрирование текста
            painter.drawText(rect, Qt.AlignCenter, "\n".join(text_parts))
