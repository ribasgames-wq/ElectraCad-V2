"""Identidade visual do ElectraCad: cores da empresa, estilo das janelas, tela de abertura e caminhos dos recursos."""
import os
import sys

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

AZUL, LARANJA, CINZA, BRANCO = '#0A2E5C', '#F58220', '#A6A6A6', '#FFFFFF'
VERSAO = '2.1'
NOME = 'ElectraCad'
SUBTITULO = 'Projetos elétricos em DWG e DXF'


def res(nome):
    """Caminho de um arquivo da pasta assets (funciona no programa instalado e na pasta de desenvolvimento)."""
    bases = []
    if getattr(sys, 'frozen', False):
        bases.append(os.path.join(getattr(sys, '_MEIPASS', os.path.dirname(sys.executable)), 'assets'))
    bases.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets'))
    for b in bases:
        p = os.path.join(b, nome)
        if os.path.isfile(p):
            return p
    return os.path.join(bases[-1], nome)


def logo():
    return QPixmap(res('logo.png'))


def app_icon():
    return QIcon(res('icon_1024.png'))


STYLE = f'''
QMainWindow, QDialog {{ background: {BRANCO}; }}
QWidget {{ color: #1c2b3d; }}
QLabel {{ background: transparent; }}
QMenuBar {{ background: {AZUL}; color: {BRANCO}; }}
QMenuBar::item {{ padding: 5px 11px; background: transparent; }}
QMenuBar::item:selected {{ background: {LARANJA}; }}
QMenu {{ background: {BRANCO}; border: 1px solid {CINZA}; }}
QMenu::item {{ padding: 5px 22px; }}
QMenu::item:selected {{ background: {LARANJA}; color: {BRANCO}; }}
QToolBar {{ background: {AZUL}; border: 0; spacing: 2px; padding: 3px; }}
QToolButton {{ color: {BRANCO}; background: transparent; padding: 4px 9px; border-radius: 4px; }}
QToolButton:hover {{ background: {LARANJA}; }}
QDockWidget {{ font-weight: 600; }}
QDockWidget::title {{ background: {AZUL}; color: {BRANCO}; padding: 6px 8px; }}
QListWidget, QTableWidget, QPlainTextEdit {{ background: {BRANCO}; border: 1px solid {CINZA}; }}
QListWidget::item:selected {{ background: {LARANJA}; color: {BRANCO}; }}
QHeaderView::section {{ background: {AZUL}; color: {BRANCO}; padding: 4px; border: 0; }}
QPushButton {{ background: {BRANCO}; border: 1px solid {CINZA}; border-radius: 4px; padding: 4px 12px; }}
QPushButton:hover {{ border-color: {LARANJA}; }}
QPushButton:default {{ background: {LARANJA}; color: {BRANCO}; border-color: {LARANJA}; }}
QPushButton:checked {{ background: {LARANJA}; color: {BRANCO}; border-color: {LARANJA}; }}
QLineEdit, QComboBox {{ background: {BRANCO}; border: 1px solid {CINZA}; border-radius: 4px; padding: 4px; }}
QLineEdit:focus, QComboBox:focus {{ border-color: {LARANJA}; }}
QStatusBar {{ background: #eef1f5; color: {AZUL}; }}
QToolButton::menu-indicator {{ image: none; }}
QToolTip {{ background: {AZUL}; color: {BRANCO}; border: 0; padding: 4px; }}
'''


def splash_pixmap(texto=''):
    W, H = 600, 340
    pm = QPixmap(W, H)
    pm.fill(QColor(BRANCO))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.fillRect(0, 0, W, 10, QColor(LARANJA))
    p.fillRect(0, H - 6, W, 6, QColor(AZUL))
    lg = logo()
    if not lg.isNull():
        lg = lg.scaledToHeight(190, Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap(48, (H - lg.height()) // 2 - 10, lg)
    f = QFont()
    f.setPixelSize(44)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor(AZUL))
    p.drawText(QRectF(190, 100, W - 200, 60), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), NOME)
    f2 = QFont()
    f2.setPixelSize(16)
    p.setFont(f2)
    p.setPen(QColor(CINZA).darker(130))
    p.drawText(QRectF(192, 160, W - 200, 28), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), SUBTITULO)
    p.setPen(QColor(LARANJA))
    p.fillRect(192, 196, 70, 4, QColor(LARANJA))
    f3 = QFont()
    f3.setPixelSize(12)
    p.setFont(f3)
    p.setPen(QColor(CINZA).darker(140))
    p.drawText(QRectF(24, H - 36, W - 48, 22), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
               texto or f'Versão {VERSAO}')
    p.end()
    return pm
