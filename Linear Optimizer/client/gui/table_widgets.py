"""
Виджеты и функции для работы с таблицами в Linear Optimizer
Адаптировано из Glass Optimizer
"""

from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QApplication
from PyQt5.QtCore import Qt, QTimer
import logging

# Настройка логирования
logger = logging.getLogger(__name__)


def _create_numeric_item(value, default=0):
    """Создание элемента таблицы для числовых значений с правильной сортировкой"""
    try:
        # Обработка различных типов данных
        if value is None:
            numeric_value = default
        elif isinstance(value, (int, float)):
            numeric_value = int(value) if isinstance(value, int) else float(value)
        elif isinstance(value, str):
            # Удаляем пробелы и проверяем на пустоту
            cleaned_value = str(value).strip()
            if cleaned_value == '' or cleaned_value.lower() in ['none', 'null', 'nan']:
                numeric_value = default
            else:
                # Пытаемся преобразовать в число
                try:
                    numeric_value = int(float(cleaned_value))
                except (ValueError, TypeError):
                    numeric_value = default
        else:
            numeric_value = default
        
        # Создаем элемент с данными
        item = QTableWidgetItem()
        item.setData(Qt.DisplayRole, numeric_value)
        
        # Устанавливаем текст для отображения
        item.setText(str(numeric_value))
        
        # Устанавливаем выравнивание по правому краю для чисел
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        return item
        
    except Exception as e:
        # Fallback: в случае любой ошибки создаем элемент со значением по умолчанию
        logger.warning(f"Error creating numeric item for value '{value}': {e}")
        item = QTableWidgetItem()
        item.setData(Qt.DisplayRole, default)
        item.setText(str(default))
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return item


def _create_text_item(value):
    """Создание элемента таблицы для текстовых значений"""
    try:
        # Обработка различных типов данных
        if value is None:
            text_value = ''
        elif isinstance(value, str):
            text_value = value.strip()
        elif isinstance(value, (int, float)):
            text_value = str(value)
        else:
            text_value = str(value) if value is not None else ''
        
        # Дополнительная очистка
        if text_value.lower() in ['none', 'null', 'nan']:
            text_value = ''
        
        # Создаем элемент
        item = QTableWidgetItem(text_value)
        
        # Устанавливаем текст явно
        item.setText(text_value)
        
        # Устанавливаем выравнивание по левому краю для текста
        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        return item
        
    except Exception as e:
        # Fallback: в случае любой ошибки создаем пустой элемент
        logger.warning(f"Error creating text item for value '{value}': {e}")
        item = QTableWidgetItem('')
        item.setText('')
        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        return item


def setup_table_columns(table: QTableWidget, headers: list):
    """Настройка столбцов таблицы"""
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    
    # Настройка размеров столбцов
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeToContents)
    
    # Последний столбец растягивается
    if len(headers) > 0:
        header.setSectionResizeMode(len(headers) - 1, QHeaderView.Stretch)


def fill_profiles_table(table: QTableWidget, profiles: list):
    """Заполнение таблицы профилей"""
    table.setRowCount(0)
    
    for profile in profiles:
        row = table.rowCount()
        table.insertRow(row)
        
        table.setItem(row, 0, _create_text_item(profile.get('element_name', '')))
        table.setItem(row, 1, _create_text_item(profile.get('profile_code', '')))
        table.setItem(row, 2, _create_numeric_item(profile.get('length', 0)))
        table.setItem(row, 3, _create_numeric_item(profile.get('quantity', 0)))
    
    # Обновляем размеры столбцов
    table.resizeColumnsToContents()


def fill_stock_remainders_table(table: QTableWidget, remainders: list):
    """Заполнение таблицы остатков со склада"""
    table.setRowCount(0)
    
    for remainder in remainders:
        row = table.rowCount()
        table.insertRow(row)
        
        table.setItem(row, 0, _create_text_item(remainder.get('profile_code', '')))
        table.setItem(row, 1, _create_numeric_item(remainder.get('length', 0)))
        table.setItem(row, 2, _create_numeric_item(remainder.get('quantity_pieces', 0)))
    
    # Обновляем размеры столбцов
    table.resizeColumnsToContents()

def fill_stock_materials_table(table: QTableWidget, materials: list):
    """Заполнение таблицы материалов со склада"""
    table.setRowCount(0)
    
    for material in materials:
        row = table.rowCount()
        table.insertRow(row)
        
        table.setItem(row, 0, _create_text_item(material.get('profile_code', '')))
        table.setItem(row, 1, _create_numeric_item(material.get('length', 0)))
        table.setItem(row, 2, _create_numeric_item(material.get('quantity_pieces', 0)))
    
    # Обновляем размеры столбцов
    table.resizeColumnsToContents()

# Для обратной совместимости оставляем старую функцию
def fill_stock_table(table: QTableWidget, stocks: list):
    """Заполнение таблицы остатков на складе (для обратной совместимости)"""
    table.setRowCount(0)
    
    for stock in stocks:
        row = table.rowCount()
        table.insertRow(row)
        
        table.setItem(row, 0, _create_numeric_item(stock.get('id', 0)))
        table.setItem(row, 1, _create_text_item(stock.get('profile_code', '')))
        table.setItem(row, 2, _create_numeric_item(stock.get('length', 0)))
        table.setItem(row, 3, _create_numeric_item(stock.get('quantity', 0)))
        table.setItem(row, 4, _create_text_item(stock.get('location', '')))
        table.setItem(row, 5, _create_text_item("Да" if stock.get('is_remainder', False) else "Нет"))
    
    # Обновляем размеры столбцов
    table.resizeColumnsToContents()


def fill_optimization_results_table(table: QTableWidget, cut_plans: list):
    """Заполнение таблицы результатов оптимизации"""
    table.setRowCount(0)
    
    for plan in cut_plans:
        row = table.rowCount()
        table.insertRow(row)
        
        # Формируем строку с распилами
        cuts_text = "; ".join([f"{cut['quantity']}x{cut['length']}" for cut in plan.cuts])
        
        table.setItem(row, 0, _create_text_item(plan.stock_id))
        table.setItem(row, 1, _create_numeric_item(plan.stock_length))
        table.setItem(row, 2, _create_text_item(cuts_text))
        table.setItem(row, 3, _create_numeric_item(plan.waste))
        table.setItem(row, 4, _create_text_item(f"{plan.waste_percent:.1f}%"))
    
    # Обновляем размеры столбцов
    table.resizeColumnsToContents()


def _ensure_table_update(table: QTableWidget):
    """Гарантирует обновление отображения таблицы"""
    try:
        # Принудительное обновление размеров столбцов
        table.resizeColumnsToContents()
        
        # Немного расширяем столбцы для лучшего вида
        header = table.horizontalHeader()
        for i in range(table.columnCount()):
            current_width = header.sectionSize(i)
            header.resizeSection(i, current_width + 20)
        
        # Обновляем виджет (убрали processEvents для избежания recursive repaint)
        # table.update() и table.viewport().update() также могут вызывать проблемы
        # Оставляем только автоматическое обновление через Qt
        
    except Exception as e:
        logger.warning(f"Error updating table display: {e}")


def _set_interactive_mode(table: QTableWidget):
    """Переключение таблицы в интерактивный режим после автоматического определения ширины"""
    try:
        header = table.horizontalHeader()
        # Переключаем все столбцы в интерактивный режим, кроме последнего
        for i in range(table.columnCount() - 1):
            header.setSectionResizeMode(i, QHeaderView.Interactive)
        # Последний столбец остается растягивающимся
        if table.columnCount() > 0:
            header.setSectionResizeMode(table.columnCount() - 1, QHeaderView.Stretch)
    except Exception as e:
        logger.warning(f"Error setting interactive mode for table: {e}")


def update_table_column_widths(table: QTableWidget):
    """Обновление ширины столбцов таблицы после заполнения данными"""
    try:
        header = table.horizontalHeader()
        # Временно переключаем в режим подгонки по содержимому
        for i in range(table.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        
        # Убрали QApplication.processEvents() - он вызывает recursive repaint
        # Размеры пересчитаются автоматически
        
        # Через короткий интервал переключаем в интерактивный режим
        QTimer.singleShot(50, lambda: _set_interactive_mode(table))
    except Exception as e:
        logger.warning(f"Error updating table column widths: {e}")


def clear_table(table: QTableWidget):
    """Очистка таблицы"""
    table.setRowCount(0)
    table.clearContents()


def enable_table_sorting(table: QTableWidget, enabled: bool = True):
    """Включение/отключение сортировки таблицы"""
    table.setSortingEnabled(enabled)


def get_selected_row_data(table: QTableWidget) -> dict:
    """Получение данных выбранной строки"""
    current_row = table.currentRow()
    if current_row < 0:
        return {}
    
    data = {}
    for col in range(table.columnCount()):
        item = table.item(current_row, col)
        if item:
            header = table.horizontalHeaderItem(col)
            key = header.text() if header else f"column_{col}"
            data[key] = item.text()
    
    return data