"""
VEO SUITE V3.2 - Dark Theme Stylesheet
======================================
File: VeoSuite_V3/ui/styles.py
"""

COLORS = {
    'primary': '#0d7377',
    'primary_hover': '#14ffec',
    'secondary': '#32e0c4',
    'sidebar_bg': '#2b2b2b',
    'content_bg': '#1e1e1e',
    'console_bg': '#0a0a0a',
    'text_primary': '#ffffff',
    'text_secondary': '#b0b0b0',
    'text_console': '#00ff41',
    'border': '#3d3d3d',
    'hover_bg': '#3a3a3a',
    'active_bg': '#0d7377',
    'danger': '#e74c3c',           # Màu lỗi/xóa
    'success': '#2ecc71'           # Màu thành công
}

DARK_THEME_STYLESHEET = """
/* VeoSuite V3 AI Factory Theme */

/* =========================================================
   1. GLOBAL & CONTAINERS
========================================================= */
QWidget {
    background-color: #121212;
    color: #FFFFFF;
    font-family: 'Segoe UI', Consolas, sans-serif;
    font-size: 13px;
}

QGroupBox {
    background-color: #1E1E1E;
    border: 1px solid #333333;
    border-radius: 6px;
    margin-top: 15px;
    padding-top: 15px;
    font-weight: bold;
    color: #00E676; /* Emerald Accent */
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 5px;
    left: 10px;
    color: #00E676;
    background-color: #1E1E1E; /* che viền phía sau */
}

/* --- SIDEBAR & NAVIGATION --- */
#sidebar {
    background-color: #1E1E1E;
    border-right: 1px solid #333333;
}

#sidebar QPushButton {
    background-color: transparent;
    color: #A0A0A0;
    border: none;
    border-left: 3px solid transparent;
    text-align: left;
    padding: 12px 20px;
    font-size: 14px;
    font-weight: 500;
}

#sidebar QPushButton:hover {
    background-color: #2D2D30;
    color: #00E676;
    border-left: 3px solid #00E676;
}

#sidebar QPushButton:checked {
    background-color: #121212;
    color: #FFFFFF;
    border-left: 3px solid #00E676;
    font-weight: bold;
}

/* =========================================================
   2. BUTTONS
========================================================= */
QPushButton {
    background-color: #2D2D30;
    color: #FFFFFF;
    border: 1px solid #444444;
    border-radius: 4px;
    padding: 6px 15px;
    font-weight: bold;
}

QPushButton:hover {
    background-color: #3E3E42;
    border: 1px solid #555555;
}

QPushButton:pressed {
    background-color: #1E1E1E;
}

QPushButton:disabled {
    background-color: #181818;
    color: #777777;
    border: 1px solid #222222;
}

/* Action Buttons (Semantic) */
QPushButton[type="action"] {
    background-color: #00E676;
    color: #000000;
    border: none;
}
QPushButton[type="action"]:hover {
    background-color: #00C853;
}

QPushButton[type="ai_magic"] {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8E2DE2, stop:1 #4A00E0);
    color: #FFFFFF;
    border: none;
}
QPushButton[type="ai_magic"]:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #9b59b6, stop:1 #8e44ad);
}

QPushButton[type="danger"] {
    background-color: #E74C3C;
    color: #FFFFFF;
    border: none;
}
QPushButton[type="danger"]:hover {
    background-color: #C0392B;
}

QPushButton[type="warning"] {
    background-color: #E67E22;
    color: #FFFFFF;
    border: none;
}
QPushButton[type="warning"]:hover {
    background-color: #D35400;
}

/* PR-5e: Semantic button "kind" — set via ui.style_kit.apply_kind(btn, "<kind>").
   Consolidates the ~70+ inline setStyleSheet(...) calls that used to
   bake colours into every tab. Keep colours in sync with
   ui/style_kit.py::KIND_COLORS. */

QPushButton[kind="primary"] {
    background-color: #3498DB;
    color: #FFFFFF;
    font-weight: bold;
    border: none;
}
QPushButton[kind="primary"]:hover {
    background-color: #2980B9;
}

QPushButton[kind="success"] {
    background-color: #27AE60;
    color: #FFFFFF;
    font-weight: bold;
    border: none;
}
QPushButton[kind="success"]:hover {
    background-color: #229954;
}

QPushButton[kind="warning"] {
    background-color: #E67E22;
    color: #FFFFFF;
    font-weight: bold;
    border: none;
}
QPushButton[kind="warning"]:hover {
    background-color: #D35400;
}

QPushButton[kind="danger"] {
    background-color: #E74C3C;
    color: #FFFFFF;
    font-weight: bold;
    border: none;
}
QPushButton[kind="danger"]:hover {
    background-color: #C0392B;
}

QPushButton[kind="info"] {
    background-color: #34495E;
    color: #FFFFFF;
    font-weight: 500;
    border: 1px solid #555555;
}
QPushButton[kind="info"]:hover {
    background-color: #3D566E;
}

QPushButton[kind="muted"] {
    background-color: #555555;
    color: #CCCCCC;
    border: 1px solid #444444;
}
QPushButton[kind="muted"]:hover {
    background-color: #666666;
}

QPushButton[kind="ai_magic"] {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8E2DE2, stop:1 #4A00E0);
    color: #FFFFFF;
    font-weight: bold;
    border: none;
}
QPushButton[kind="ai_magic"]:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #9B59B6, stop:1 #8E44AD);
}

/* PR-5e: Coloured group-box "accent" — set via ui.style_kit.apply_accent(grp, "<accent>").
   Consolidates the per-tab inline border colours (Edge TTS green,
   OpenAI purple, Google red, Custom yellow, Proxy blue, ...). Keep
   colours in sync with ui/style_kit.py::ACCENT_COLORS. */

QGroupBox[accent="emerald"] {
    border: 1px solid #2ECC71;
    font-weight: bold;
    margin-top: 10px;
}
QGroupBox[accent="emerald"]::title { color: #2ECC71; }

QGroupBox[accent="lilac"] {
    border: 1px solid #9B59B6;
    font-weight: bold;
    margin-top: 10px;
}
QGroupBox[accent="lilac"]::title { color: #9B59B6; }

QGroupBox[accent="red"] {
    border: 1px solid #E74C3C;
    font-weight: bold;
    margin-top: 10px;
}
QGroupBox[accent="red"]::title { color: #E74C3C; }

QGroupBox[accent="amber"] {
    border: 1px solid #F1C40F;
    font-weight: bold;
    margin-top: 10px;
}
QGroupBox[accent="amber"]::title { color: #F1C40F; }

QGroupBox[accent="blue"] {
    border: 1px solid #3498DB;
    font-weight: bold;
    margin-top: 10px;
}
QGroupBox[accent="blue"]::title { color: #3498DB; }

QGroupBox[accent="slate"] {
    border: 1px solid #555555;
    font-weight: bold;
    margin-top: 10px;
}
QGroupBox[accent="slate"]::title { color: #AAAAAA; }

QGroupBox[accent="cyan"] {
    border: 1px solid #00E6E6;
    background: #252526;
    font-weight: bold;
    margin-top: 10px;
}
QGroupBox[accent="cyan"]::title { color: #00E6E6; }

/* PR-5e: Named-object selectors for recurring widget patterns. */

QLabel#hintLabel {
    color: #AAAAAA;
    font-style: italic;
}

QLabel#adminTitleLabel {
    font-size: 18px;
    font-weight: bold;
    color: #F1C40F;
    margin-bottom: 10px;
}

QLabel#sectionTitleLabel {
    font-size: 18px;
    font-weight: bold;
    color: #00E6E6;
    padding: 5px;
}

QTabWidget#adminSubTabs::pane {
    border: 1px solid #444444;
}
QTabWidget#adminSubTabs QTabBar::tab {
    min-width: 150px;
    padding: 8px 16px;
}

QScrollArea#transparentScroll {
    border: none;
    background: transparent;
}

QPushButton#externalLinkButton {
    color: #3498DB;
    background: transparent;
    border: 1px dashed #3498DB;
}
QPushButton#externalLinkButton:hover {
    color: #5DADE2;
    border: 1px dashed #5DADE2;
}

QLabel#infoBanner {
    background: #2C3E50;
    padding: 10px;
    border-radius: 5px;
}

QFrame#statsCard {
    background: #252526;
    border-radius: 6px;
    padding: 10px;
}

QTextEdit#consoleArea {
    background: #0A0A0A;
    color: #00E676;
    font-family: 'Consolas', monospace;
    font-size: 12px;
    border: none;
}

QFrame#editorHeader {
    background: #252526;
    border-bottom: 1px solid #333333;
}

QFrame#previewContainer {
    background: #000000;
    border: 2px solid #444444;
}

QLabel#subtitleOverlay {
    color: #FFFFFF;
    font-size: 18px;
    font-weight: bold;
    background: rgba(0, 0, 0, 100);
    padding: 5px;
}

QFrame#propertyPanel {
    background: #1E1E1E;
    border-left: 1px solid #333333;
}

QLabel#timelineLabel {
    font-weight: bold;
    margin-top: 10px;
}

QScrollArea#timelineScroll {
    background: #252526;
    border: none;
}

QScrollArea#contentEditorScroll {
    border: none;
    background: #2D2D30;
}

QFrame#contentActionBar {
    background: #252526;
    border-top: 1px solid #3E3E42;
}

QFrame#controlContainer {
    background: #252526;
    border-top: 2px solid #444444;
}

QFrame#mediaActionBar {
    background: #252526;
    border-bottom: 1px solid #333333;
}

QScrollArea#mediaBenchScroll {
    border: none;
    background: #1E1E1E;
}

/* QProgressBar variant selectors. The default chunk colour is #00E676 (green);
   widgets that prefer the blue/primary accent set:
       widget.setProperty("chunkColor", "primary")
   and the QSS engine re-polishes them automatically. */
QProgressBar[chunkColor="primary"]::chunk { background-color: #3498DB; }
QProgressBar[chunkColor="warning"]::chunk { background-color: #F39C12; }
QProgressBar[chunkColor="danger"]::chunk { background-color: #E74C3C; }

/* =========================================================
   3. INPUTS & LISTS
========================================================= */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {
    background-color: #181818;
    color: #FFFFFF;
    border: 1px solid #333333;
    border-radius: 4px;
    padding: 6px;
    selection-background-color: #8E2DE2;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #00E676 !important;
}

QComboBox {
    background-color: #181818;
    border: 1px solid #333333;
    border-radius: 4px;
    padding: 5px;
    min-height: 25px;
}
QComboBox:focus {
    border: 1px solid #00E676 !important;
}
QComboBox::drop-down {
    border: none;
}
QComboBox QAbstractItemView {
    background-color: #1E1E1E;
    border: 1px solid #333333;
    selection-background-color: #2D2D30;
}

QListWidget, QTableWidget {
    background-color: #181818;
    alternate-background-color: #1E1E1E;
    border: 1px solid #333333;
    border-radius: 4px;
    outline: none;
    gridline-color: #333333;
}
QListWidget::item, QTableWidget::item {
    padding: 5px;
}
QListWidget::item:selected, QTableWidget::item:selected {
    background-color: #2D2D30;
    color: #00E676;
    font-weight: bold;
    border-left: 3px solid #00E676;
}
QHeaderView::section {
    background-color: #1E1E1E;
    color: #A0A0A0;
    padding: 5px;
    border: 1px solid #333333;
    font-weight: bold;
}

/* =========================================================
   4. SCROLLBARS
========================================================= */
QScrollBar:vertical {
    border: none;
    background: #121212;
    width: 10px;
    margin: 0px 0px 0px 0px;
}
QScrollBar::handle:vertical {
    background: #333333;
    min-height: 20px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: #555555;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    border: none;
    background: #121212;
    height: 10px;
    margin: 0px 0px 0px 0px;
}
QScrollBar::handle:horizontal {
    background: #333333;
    min-width: 20px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal:hover {
    background: #555555;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* =========================================================
   5. PROGRESS BARS
========================================================= */
QProgressBar {
    background-color: #181818;
    border: 1px solid #333333;
    border-radius: 4px;
    text-align: center;
    color: #FFFFFF;
    font-weight: bold;
}
QProgressBar::chunk {
    background-color: #00E676;
    border-radius: 3px;
}

/* =========================================================
   6. TABS & SPLITTER
========================================================= */
QTabWidget::pane {
    border: 1px solid #333333;
    border-radius: 4px;
    background: #121212;
}

QTabBar::tab {
    background: #1E1E1E;
    color: #A0A0A0;
    border: 1px solid #333333;
    border-bottom: none;
    padding: 8px 16px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}

QTabBar::tab:selected {
    background: #121212;
    color: #00E676;
    font-weight: bold;
    border-top: 2px solid #00E676;
}

QTabBar::tab:hover:!selected {
    background: #2D2D30;
}

QSplitter::handle {
    background-color: #333333;
}
QSplitter::handle:hover {
    background-color: #00E676;
}

/* --- CONSOLE LOG --- */
#consoleWidget {
    background-color: #0A0A0A;
    border-top: 1px solid #00E676;
}

#consoleTextEdit {
    background-color: #0A0A0A;
    color: #00E676;
    font-family: 'Consolas', monospace;
    font-size: 12px;
    border: none;
}
"""

DEPARTMENT_ICONS = {
    'radar': '🎯',
    'content': '✍️',
    'assets': '🎨',
    'render': '🎬',
    'publisher': '📡',
    'ops': '⚙️'
}
