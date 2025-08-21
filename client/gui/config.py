"""
Конфигурация стилей и настроек GUI для Linear Optimizer
Адаптировано из Glass Optimizer
"""

# Основные темные стили для приложения
MAIN_WINDOW_STYLE = """
QWidget {
    background-color: #2b2b2b;
    color: #ffffff;
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 10pt;
}

QGroupBox {
    background-color: #3c3c3c;
    border: 2px solid #555555;
    border-radius: 8px;
    margin: 5px;
    padding-top: 15px;
    font-weight: bold;
    color: #ffffff;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 8px 0 8px;
    color: #ffffff;
    background-color: #3c3c3c;
}

QPushButton {
    background-color: #0078d4;
    color: white;
    border: none;
    padding: 8px 16px;
    border-radius: 4px;
    font-weight: bold;
    min-width: 100px;
}

QPushButton:hover {
    background-color: #106ebe;
}

QPushButton:pressed {
    background-color: #005a9e;
}

QPushButton:disabled {
    background-color: #555555;
    color: #888888;
}

QLineEdit {
    background-color: #404040;
    border: 2px solid #555555;
    border-radius: 4px;
    padding: 6px;
    color: #ffffff;
}

QLineEdit:focus {
    border-color: #0078d4;
}

QTableWidget {
    background-color: #404040;
    alternate-background-color: #4a4a4a;
    gridline-color: #555555;
    border: 1px solid #555555;
    border-radius: 4px;
    color: #ffffff;
}

QTableWidget::item {
    padding: 8px;
    border-bottom: 1px solid #555555;
}

QTableWidget::item:selected {
    background-color: #0078d4;
    color: white;
}

QHeaderView::section {
    background-color: #2b2b2b;
    color: #ffffff;
    padding: 8px;
    border: 1px solid #555555;
    font-weight: bold;
}

QLabel {
    color: #ffffff;
    background-color: transparent;
}

QSpinBox, QComboBox {
    background-color: #404040;
    border: 2px solid #555555;
    border-radius: 4px;
    padding: 6px;
    color: #ffffff;
    min-width: 80px;
}

QSpinBox:focus, QComboBox:focus {
    border-color: #0078d4;
}

QComboBox::drop-down {
    border: none;
    background-color: #555555;
    width: 20px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 5px solid #ffffff;
    margin: 5px;
}

QMessageBox {
    background-color: #2b2b2b;
    color: #ffffff;
}

QMessageBox QPushButton {
    background-color: #0078d4;
    color: white;
    border: none;
    padding: 8px 16px;
    border-radius: 4px;
    font-weight: bold;
    min-width: 80px;
}

QMessageBox QPushButton:hover {
    background-color: #106ebe;
}

QCheckBox {
    color: #ffffff;
    spacing: 8px;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 2px solid #555555;
    border-radius: 3px;
    background-color: #404040;
}

QCheckBox::indicator:checked {
    background-color: #0078d4;
    border-color: #0078d4;
    image: none;
}

QProgressBar {
    background-color: #404040;
    border: 2px solid #555555;
    border-radius: 4px;
    text-align: center;
    color: #ffffff;
    font-weight: bold;
}

QProgressBar::chunk {
    background-color: #0078d4;
    border-radius: 2px;
}

QSplitter::handle {
    background-color: #555555;
    width: 3px;
    height: 3px;
}

QSplitter::handle:hover {
    background-color: #0078d4;
}

QMenuBar {
    background-color: #2b2b2b;
    color: #ffffff;
    border-bottom: 1px solid #555555;
}

QMenuBar::item {
    background-color: transparent;
    padding: 4px 8px;
}

QMenuBar::item:selected {
    background-color: #0078d4;
}

QMenu {
    background-color: #3c3c3c;
    color: #ffffff;
    border: 1px solid #555555;
}

QMenu::item {
    padding: 8px 16px;
}

QMenu::item:selected {
    background-color: #0078d4;
}

QToolBar {
    background-color: #2b2b2b;
    border: 1px solid #555555;
    color: #ffffff;
}

QToolBar::separator {
    background-color: #555555;
    width: 2px;
    margin: 2px;
}

QStatusBar {
    background-color: #2b2b2b;
    color: #ffffff;
    border-top: 1px solid #555555;
}
"""

# Стили для вкладок
TAB_STYLE = """
QTabWidget::pane {
    border: 2px solid #555555;
    background-color: #3c3c3c;
    border-radius: 8px;
}

QTabBar::tab {
    background-color: #2b2b2b;
    color: #ffffff;
    padding: 10px 20px;
    margin-right: 3px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    border: 2px solid #555555;
    border-bottom: none;
    font-weight: bold;
    font-size: 9pt;
    min-width: 200px;
    max-width: 300px;
}

QTabBar::tab:selected {
    background-color: #3c3c3c;
    border-bottom: 2px solid #0078d4;
    color: #ffffff;
    font-size: 9pt;
}

QTabBar::tab:hover:!selected {
    background-color: #404040;
}
"""

# Стили для диалогов
DIALOG_STYLE = """
QDialog {
    background-color: #2b2b2b;
    color: #ffffff;
    font-family: 'Segoe UI', Arial, sans-serif;
}

QLabel {
    color: #ffffff;
    background-color: transparent;
}

QTextEdit {
    background-color: #404040;
    border: 2px solid #555555;
    border-radius: 4px;
    color: #ffffff;
    font-family: 'Consolas', monospace;
}

QPushButton {
    background-color: #0078d4;
    color: white;
    border: none;
    padding: 8px 16px;
    border-radius: 4px;
    font-weight: bold;
    min-width: 80px;
}

QPushButton:hover {
    background-color: #106ebe;
}

QPushButton:pressed {
    background-color: #005a9e;
}

QProgressBar {
    background-color: #404040;
    border: 2px solid #555555;
    border-radius: 4px;
    text-align: center;
    color: #ffffff;
    font-weight: bold;
}

QProgressBar::chunk {
    background-color: #28a745;
    border-radius: 2px;
}
"""

# Специальные стили для кнопок
SPECIAL_BUTTON_STYLES = {
    "optimize": """
        QPushButton {
            background-color: #28a745;
            color: white;
            font-weight: bold;
            font-size: 11pt;
            padding: 10px 20px;
            min-width: 200px;
        }
        QPushButton:hover {
            background-color: #218838;
        }
        QPushButton:disabled {
            background-color: #555555;
            color: #888888;
        }
    """,
    
    "save_settings": """
        QPushButton {
            background-color: #0078d4;
            color: white;
            font-weight: bold;
            font-size: 11pt;
            padding: 10px 20px;
            min-width: 250px;
        }
        QPushButton:hover {
            background-color: #106ebe;
        }
    """,
    
    "upload": """
        QPushButton {
            background-color: #0078d4;
            color: white;
            font-weight: bold;
            padding: 12px 24px;
            border: none;
            border-radius: 6px;
            font-size: 12pt;
            margin: 10px 0px;
        }
        QPushButton:hover {
            background-color: #106ebe;
        }
        QPushButton:pressed {
            background-color: #005a9e;
        }
        QPushButton:disabled {
            background-color: #666666;
            color: #cccccc;
        }
    """,
    
    "copy": """
        QPushButton {
            background-color: #4CAF50;
            color: white;
            font-weight: bold;
            padding: 8px 16px;
            border: none;
            border-radius: 4px;
            font-size: 10pt;
            min-width: 120px;
        }
        QPushButton:hover {
            background-color: #45a049;
        }
        QPushButton:pressed {
            background-color: #3d8b40;
        }
        QPushButton:disabled {
            background-color: #666666;
            color: #cccccc;
        }
    """,
    
    "copy_csv": """
        QPushButton {
            background-color: #2196F3;
            color: white;
            font-weight: bold;
            padding: 8px 16px;
            border: none;
            border-radius: 4px;
            font-size: 10pt;
            min-width: 120px;
        }
        QPushButton:hover {
            background-color: #1976D2;
        }
        QPushButton:pressed {
            background-color: #1565C0;
        }
        QPushButton:disabled {
            background-color: #666666;
            color: #cccccc;
        }
    """
}

# Настройки для конкретных виджетов
WIDGET_CONFIGS = {
    "target_waste_percent": """
        QSpinBox {
            background-color: #404040;
            color: #00ff00;
            font-weight: bold;
            font-size: 12pt;
        }
    """,
    
    "info_label": """
        QLabel {
            font-size: 12pt;
            font-weight: bold;
            padding: 12px;
            background-color: #404040;
            border-radius: 6px;
            border: 2px solid #555555;
        }
    """,
    
    "stats_labels": {
        "default": "color: #ffffff; font-weight: bold; background-color: transparent; font-size: 11pt;",
        "remnants": "color: #4ecdc4; font-weight: bold; background-color: transparent; font-size: 11pt;",
        "waste": "color: #ff6b6b; font-weight: bold; background-color: transparent; font-size: 11pt;"
    }
}

# Цветовая схема
COLORS = {
    "primary": "#0078d4",
    "primary_hover": "#106ebe", 
    "primary_pressed": "#005a9e",
    "success": "#28a745",
    "success_hover": "#218838",
    "warning": "#ffc107",
    "danger": "#dc3545",
    "background_main": "#2b2b2b",
    "background_secondary": "#3c3c3c",
    "background_input": "#404040",
    "border_color": "#555555",
    "text_primary": "#ffffff",
    "text_secondary": "#cccccc",
    "text_disabled": "#888888",
    "accent_green": "#4ecdc4",
    "accent_red": "#ff6b6b",
    "accent_yellow": "#00ff00"
}