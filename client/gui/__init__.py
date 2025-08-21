"""
GUI модуль для Linear Optimizer
Современный интерфейс для оптимизации линейного распила профилей
"""

from .main_window import LinearOptimizerWindow
from .dialogs import DebugDialog, ProgressDialog, OptimizationSettingsDialog, ApiSettingsDialog
from .table_widgets import (
    setup_table_columns, fill_profiles_table, fill_stock_table,
    fill_optimization_results_table, update_table_column_widths,
    clear_table, enable_table_sorting, copy_table_to_clipboard, copy_table_as_csv
)
from .config import (
    MAIN_WINDOW_STYLE, TAB_STYLE, DIALOG_STYLE, 
    SPECIAL_BUTTON_STYLES, WIDGET_CONFIGS, COLORS
)

__all__ = [
    'LinearOptimizerWindow',
    'DebugDialog', 
    'ProgressDialog', 
    'OptimizationSettingsDialog', 
    'ApiSettingsDialog',
    'setup_table_columns',
    'fill_profiles_table',
    'fill_stock_table', 
    'fill_optimization_results_table',
    'update_table_column_widths',
    'clear_table',
    'enable_table_sorting',
    'copy_table_to_clipboard',
    'copy_table_as_csv',
    'MAIN_WINDOW_STYLE',
    'TAB_STYLE',
    'DIALOG_STYLE',
    'SPECIAL_BUTTON_STYLES',
    'WIDGET_CONFIGS',
    'COLORS'
]