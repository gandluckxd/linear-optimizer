"""
Виджеты и функции для работы с таблицами в Linear Optimizer
Адаптировано из Glass Optimizer
"""

from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QApplication
from PyQt5.QtCore import Qt, QTimer
from PyQt5 import QtCore
from PyQt5.QtGui import QColor
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
    """Заполнение таблицы результатов оптимизации с новой структурой столбцов"""
    table.setRowCount(0)
    
    for i, plan in enumerate(cut_plans):
        try:
            row = table.rowCount()
            table.insertRow(row)
            
            # 1. Артикул (берем из первого распила)
            profile_code = ""
            if plan.cuts and len(plan.cuts) > 0:
                first_cut = plan.cuts[0]
                if isinstance(first_cut, dict) and 'profile_code' in first_cut:
                    profile_code = first_cut['profile_code']
            table.setItem(row, 0, _create_text_item(profile_code))
            
            # 2. Длина хлыста (мм)
            table.setItem(row, 1, _create_numeric_item(plan.stock_length))
            
            # 3. Количество хлыстов такого распила
            count = getattr(plan, 'count', 1)
            table.setItem(row, 2, _create_numeric_item(count))
            
            # 4. Количество деталей на хлысте
            cuts_count = plan.get_cuts_count()
            table.setItem(row, 3, _create_numeric_item(cuts_count))
            
            # 5. Распил (форматируем распилы)
            cuts_parts = []
            for cut in plan.cuts:
                if isinstance(cut, dict) and 'quantity' in cut and 'length' in cut:
                    cuts_parts.append(f"{cut['quantity']}x{cut['length']}")
                else:
                    cuts_parts.append("ERROR")
            cuts_text = "; ".join(cuts_parts) if cuts_parts else "Нет распилов"
            
            # Добавляем индикатор статуса
            is_valid = plan.validate(5.0)
            if not is_valid:
                cuts_text += " ⚠️ ОШИБКА"
            elif plan.get_used_length(5.0) > plan.stock_length * 0.95:
                cuts_text += " ⚡ ПЛОТНО"
            else:
                cuts_text += " ✅ ОК"
            
            table.setItem(row, 4, _create_text_item(cuts_text))
            
            # 6. Деловой остаток (мм)
            remainder = getattr(plan, 'remainder', None)
            remainder_length = remainder if remainder and remainder > 0 else 0
            table.setItem(row, 5, _create_numeric_item(remainder_length))
            
            # 7. Деловой остаток (%)
            remainder_percent = (remainder_length / plan.stock_length * 100) if plan.stock_length > 0 and remainder_length > 0 else 0
            table.setItem(row, 6, _create_text_item(f"{remainder_percent:.1f}%"))
            
            # 8. Отход (мм)
            waste_length = plan.stock_length - plan.get_used_length(5.0)
            table.setItem(row, 7, _create_numeric_item(waste_length))
            
            # 9. Отход (%)
            waste_percent = (waste_length / plan.stock_length * 100) if plan.stock_length > 0 else 0
            table.setItem(row, 8, _create_text_item(f"{waste_percent:.1f}%"))
            
            # Создаем детальный tooltip для всех планов
            used_length = plan.get_used_length(5.0)
            total_pieces_length = plan.get_total_pieces_length()
            saw_width_total = 5.0 * (cuts_count - 1) if cuts_count > 1 else 0
            
            tooltip_lines = [
                f"📊 Детальная информация:",
                f"Длина хлыста: {plan.stock_length:.0f}мм",
                f"Количество деталей: {cuts_count}шт",
                f"Количество одинаковых хлыстов: {getattr(plan, 'count', 1)}",
                f"Сумма длин деталей: {total_pieces_length:.0f}мм",
                f"Ширина пропилов: {saw_width_total:.0f}мм",
                f"Общая использованная длина: {used_length:.0f}мм",
            ]
            
            # Добавляем информацию о деловом остатке
            if plan.is_remainder and hasattr(plan, 'warehouseremaindersid') and plan.warehouseremaindersid:
                tooltip_lines.append(f"🏷️ ID делового остатка: {plan.warehouseremaindersid}")
            
            # Добавляем информацию об отходах и остатках
            if remainder and remainder > 0:
                tooltip_lines.append(f"🔨 Деловой остаток: {remainder_length:.0f}мм ({remainder_percent:.1f}%) - пригоден для использования")
                tooltip_lines.append(f"🗑️ Отходы: {waste_length:.0f}мм ({waste_percent:.1f}%) - непригодный материал")
                tooltip_lines.append(f"📏 Всего неиспользовано: {waste_length:.0f}мм")
            else:
                tooltip_lines.append(f"🗑️ Отходы: {waste_length:.0f}мм ({waste_percent:.1f}%) - весь неиспользованный материал")
                tooltip_lines.append(f"🔨 Деловых остатков: нет (< {300}мм)")
            
            tooltip_lines.append(f"Статус: {'✅ Корректно' if is_valid else '❌ ОШИБКА - превышена длина хлыста!'}")
            
            if not is_valid:
                tooltip_lines.append(f"⚠️ ПРЕВЫШЕНИЕ: {used_length - plan.stock_length:.0f}мм")
            
            tooltip = "\n".join(tooltip_lines)
            
            # Применяем tooltip ко всем ячейкам строки
            for col in range(table.columnCount()):
                item = table.item(row, col)
                if item:
                    item.setToolTip(tooltip)
                    # Цветовая индикация для проблемных планов
                    try:
                        if not is_valid:
                            # Красный фон для ошибочных планов
                            item.setBackground(QColor(255, 200, 200))  # Светло-красный
                        elif used_length > plan.stock_length * 0.95:
                            # Желтый фон для плотных планов
                            item.setBackground(QColor(255, 255, 200))  # Светло-желтый
                    except Exception as color_error:
                        print(f"⚠️ Ошибка установки цвета: {color_error}")
                        # Продолжаем без цвета
                        
        except Exception as e:
            print(f"⚠️ Ошибка при отображении плана {plan.stock_id if hasattr(plan, 'stock_id') else 'unknown'}: {e}")
            # Создаем строку с ошибкой
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, _create_text_item("ERROR"))
            table.setItem(row, 1, _create_text_item("ERROR"))
            table.setItem(row, 2, _create_text_item("ERROR"))
            table.setItem(row, 3, _create_text_item("ERROR"))
            table.setItem(row, 4, _create_text_item(f"Ошибка: {str(e)}"))
            table.setItem(row, 5, _create_text_item("ERROR"))
            table.setItem(row, 6, _create_text_item("ERROR"))
            table.setItem(row, 7, _create_text_item("ERROR"))
            table.setItem(row, 8, _create_text_item("ERROR"))
    
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


def copy_table_to_clipboard(table: QTableWidget):
    """Копирует всю таблицу в буфер обмена в текстовом формате"""
    try:
        if table.rowCount() == 0:
            return False
        
        # Получаем заголовки
        headers = []
        for col in range(table.columnCount()):
            header_item = table.horizontalHeaderItem(col)
            headers.append(header_item.text() if header_item else f"Столбец {col + 1}")
        
        # Собираем данные
        rows_data = []
        
        # Добавляем заголовки
        rows_data.append("\t".join(headers))
        
        # Добавляем данные строк
        for row in range(table.rowCount()):
            row_data = []
            for col in range(table.columnCount()):
                item = table.item(row, col)
                if item:
                    row_data.append(item.text())
                else:
                    row_data.append("")
            rows_data.append("\t".join(row_data))
        
        # Объединяем все в одну строку с переносами
        table_text = "\n".join(rows_data)
        
        # Копируем в буфер обмена
        clipboard = QApplication.clipboard()
        clipboard.setText(table_text)
        
        return True
        
    except Exception as e:
        logger.error(f"Error copying table to clipboard: {e}")
        return False


def copy_table_as_csv(table: QTableWidget):
    """Копирует всю таблицу в буфер обмена в формате CSV"""
    try:
        if table.rowCount() == 0:
            return False
        
        # Получаем заголовки
        headers = []
        for col in range(table.columnCount()):
            header_item = table.horizontalHeaderItem(col)
            headers.append(header_item.text() if header_item else f"Столбец {col + 1}")
        
        # Собираем данные
        rows_data = []
        
        # Добавляем заголовки
        rows_data.append(",".join(f'"{header}"' for header in headers))
        
        # Добавляем данные строк
        for row in range(table.rowCount()):
            row_data = []
            for col in range(table.columnCount()):
                item = table.item(row, col)
                if item:
                    # Экранируем кавычки и запятые
                    cell_text = item.text().replace('"', '""')
                    row_data.append(f'"{cell_text}"')
                else:
                    row_data.append('""')
            rows_data.append(",".join(row_data))
        
        # Объединяем все в одну строку с переносами
        csv_text = "\n".join(rows_data)
        
        # Копируем в буфер обмена
        clipboard = QApplication.clipboard()
        clipboard.setText(csv_text)
        
        return True
        
    except Exception as e:
        logger.error(f"Error copying table as CSV: {e}")
        return False