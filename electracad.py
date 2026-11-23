"""ElectraCad - editor e visualizador de DXF/DWG 2D para macOS (PyQt6 + ezdxf)."""
import sys
import os
import math
import traceback
import faulthandler
from datetime import datetime
from itertools import islice

from PyQt6.QtCore import Qt, QPointF, QRectF, QSettings, QTimer, QMarginsF, QSize
from PyQt6.QtGui import (QPainter, QPen, QColor, QPolygonF, QTransform, QAction, QFont, QKeySequence,
                         QPixmap, QIcon, QPdfWriter, QPageSize, QPageLayout)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel,
                             QPushButton, QFileDialog, QDialog, QPlainTextEdit, QDockWidget, QListWidget,
                             QListWidgetItem, QInputDialog, QToolBar, QTableWidget, QTableWidgetItem, QComboBox,
                             QHeaderView, QAbstractItemView, QSplashScreen, QToolButton, QMenu, QSizePolicy, QFormLayout)
import ezdxf
from ezdxf import path as ezpath, colors, recover
from ezdxf.math import Matrix44, Vec3
from ezdxf.addons import odafc

import geom
import estilo
import dwgconv
import marca
import folha
import projeto_io
import unifilar
import re
import eletrica as E

# ---------------------------------------------------------------- proteção contra erros
LOG = os.path.join(os.path.expanduser('~'), 'ElectraCad_erro.log')
try:
    _logfile = open(LOG, 'a', buffering=1, encoding='utf-8')
    faulthandler.enable(_logfile)  # registra também quedas graves do Python
except OSError:
    _logfile = None
_shown, _busy = set(), [False]


def alert(parent, title, text, buttons=('OK',), detail=None, default=0):
    """Janela de aviso própria (widgets comuns do Qt).

    NÃO usa QMessageBox: no macOS 27 a caixa de mensagem nativa (NSAlert) derruba o programa inteiro
    ao calcular o layout (confirmado no relatório de queda do sistema). Devolve o índice do botão
    clicado, ou None se a janela foi fechada com Esc.
    """
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setModal(True)
    dlg.setMinimumWidth(460)
    lay = QVBoxLayout(dlg)
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    lay.addWidget(lbl)
    if detail:
        te = QPlainTextEdit(detail)
        te.setReadOnly(True)
        te.setMinimumSize(520, 200)
        lay.addWidget(te)
    row = QHBoxLayout()
    row.addStretch(1)
    res = [None]

    def choose(i):
        res[0] = i
        dlg.accept()
    for i, name in enumerate(buttons):
        b = QPushButton(name)
        b.clicked.connect(lambda _=False, i=i: choose(i))
        if i == default:
            b.setDefault(True)
        row.addWidget(b)
    lay.addLayout(row)
    dlg.exec()
    return res[0]


def log_exc(note=''):
    """Grava o erro atual no arquivo de registro (sem mostrar nada)."""
    txt = traceback.format_exc()
    sys.stderr.write(txt)
    if _logfile:
        try:
            _logfile.write(f'--- {datetime.now():%Y-%m-%d %H:%M:%S} {note}\n{txt}\n')
        except Exception:
            pass
    return txt


def _show_error(txt):
    try:
        alert(None, 'ElectraCad', 'Ocorreu um erro, mas o programa continua aberto.\n\n'
              f'Se o problema se repetir, envie o arquivo:\n{LOG}', detail=txt)
    finally:
        _busy[0] = False


def excepthook(et, ev, tb):
    """Em vez de fechar o programa (comportamento padrão do PyQt6), mostra o erro e grava no log."""
    txt = ''.join(traceback.format_exception(et, ev, tb))
    sys.stderr.write(txt)
    if _logfile:
        try:
            _logfile.write(f'--- {datetime.now():%Y-%m-%d %H:%M:%S}\n{txt}\n')
        except Exception:
            pass
    key = txt.strip().splitlines()[-1]
    if key in _shown or _busy[0] or QApplication.instance() is None:
        return
    _shown.add(key)
    _busy[0] = True
    QTimer.singleShot(0, lambda: _show_error(txt))


sys.excepthook = excepthook

# ---------------------------------------------------------------- constantes
BG, ACC, FG, GUIDE = QColor(255, 255, 255), QColor(245, 130, 32), QColor(10, 46, 92), QColor(0, 150, 90)
LIGHT = True   # fundo claro (padrão, cores da empresa); Exibir > Fundo escuro inverte


def set_theme(light):
    global BG, FG, GUIDE, LIGHT
    LIGHT = light
    BG, FG, GUIDE = ((QColor(255, 255, 255), QColor(10, 46, 92), QColor(0, 150, 90)) if light else
                     (QColor(20, 24, 29), QColor(235, 240, 245), QColor(0, 230, 120)))


def adapt_color(c, plot=False):
    """Cores claras demais para o fundo branco (e o branco do papel) ficam legíveis."""
    if not (plot or LIGHT):
        return c
    r, g, b = c.red(), c.green(), c.blue()
    if min(r, g, b) > 200:
        return QColor(20, 24, 29)
    lum = .299 * r + .587 * g + .114 * b
    if lum > 150:
        k = 150 / lum
        return QColor(int(r * k), int(g * k), int(b * k))
    return c
CMDS = {'L': 'LINE', 'LINE': 'LINE', 'PL': 'PLINE', 'PLINE': 'PLINE', 'REC': 'RECT', 'RECT': 'RECT',
        'C': 'CIRCLE', 'CIRCLE': 'CIRCLE', 'A': 'ARC', 'ARC': 'ARC', 'T': 'TEXT', 'TEXT': 'TEXT',
        'M': 'MOVE', 'MOVE': 'MOVE', 'CO': 'COPY', 'CP': 'COPY', 'COPY': 'COPY',
        'RO': 'ROTATE', 'ROTATE': 'ROTATE', 'SC': 'SCALE', 'SCALE': 'SCALE',
        'MI': 'MIRROR', 'MIRROR': 'MIRROR', 'O': 'OFFSET', 'OFFSET': 'OFFSET',
        'TR': 'TRIM', 'TRIM': 'TRIM', 'EX': 'EXTEND', 'EXTEND': 'EXTEND', 'F': 'FILLET', 'FILLET': 'FILLET',
        'X': 'EXPLODE', 'EXPLODE': 'EXPLODE', 'E': 'ERASE', 'ERASE': 'ERASE', 'DEL': 'ERASE',
        'U': 'UNDO', 'UNDO': 'UNDO', 'ZE': 'ZOOM', 'ZOOM': 'ZOOM', 'ZW': 'ZOOMW',
        'DI': 'DIST', 'DIST': 'DIST', 'DLI': 'DIMLINEAR', 'DAL': 'DIMALIGNED',
        'LA': 'LAYER', 'LAYER': 'LAYER',
        'SIM': 'SYMBOL', 'SYMBOL': 'SYMBOL', 'CONTAR': 'COUNT', 'LEGENDA': 'LEGEND', 'QC': 'QCARGAS',
        'PDF': 'PDF', 'ELE': 'ELEC_LAYERS', 'ET': 'CONDUIT_T', 'EP': 'CONDUIT_P', 'FOLHA': 'SHEET', 'UNI': 'UNIFILAR', 'CABOS': 'CABOS', 'LM': 'BOM', 'FOCO': 'FOCUS', 'GRADE': 'GRID', 'ORTHO': 'ORTHO', 'POLAR': 'POLAR', 'SNAP': 'SNAP'}
ACTIONS = {'COUNT': 'count_symbols', 'LEGEND': 'legend', 'QCARGAS': 'qcargas', 'PDF': 'export_pdf',
           'ELEC_LAYERS': 'elec_layers', 'SHEET': 'sheet_dialog', 'UNIFILAR': 'start_unifilar', 'CABOS': 'export_cables', 'BOM': 'export_bom', 'FOCUS': 'toggle_focus',
           'GRID': 'toggle_grid', 'CONDUIT_T': 'conduit_teto', 'CONDUIT_P': 'conduit_piso'}
DEFAULT_LC = (True, 7, 'CONTINUOUS', -3)
SELCMDS = ('MOVE', 'COPY', 'ROTATE', 'SCALE', 'MIRROR', 'ERASE', 'EXPLODE')
PICKCMDS = ('OFFSET', 'TRIM', 'EXTEND', 'FILLET')
DRAW_REL = ('LINE', 'PLINE', 'MOVE', 'COPY', 'MIRROR')  # comandos em que orto/polar valem
PROMPT = {
    'LINE': 'LINE: clique o ponto inicial e os seguintes. Digite uma distância + Enter para medir na direção do mouse. Enter encerra.',
    'PLINE': 'PLINE: clique os vértices. Enter finaliza, C fecha.',
    'RECT': 'RECT: clique dois cantos opostos.',
    'CIRCLE': 'CIRCLE: clique o centro, depois clique ou digite o raio.',
    'ARC': 'ARC: clique o ponto inicial, um ponto no meio do arco e o ponto final.',
    'TEXT': 'TEXT: clique onde o texto deve ficar.',
    'MOVE': 'MOVE: clique o ponto base e depois o destino (ou digite a distância).',
    'COPY': 'COPY: clique o ponto base e depois cada destino. Enter encerra.',
    'ROTATE': 'ROTATE: clique o ponto base, depois clique o ângulo ou digite os graus.',
    'SCALE': 'SCALE: clique o ponto base e digite o fator (ex.: 2).',
    'MIRROR': 'MIRROR: clique dois pontos da linha de espelho. O original é mantido.',
    'OFFSET': 'OFFSET: digite a distância e tecle Enter.',
    'TRIM': 'TRIM: clique o trecho da linha que deve sumir. Esc encerra.',
    'EXTEND': 'EXTEND: clique perto da ponta da linha que deve crescer até o próximo objeto. Esc encerra.',
    'FILLET': 'FILLET: clique a primeira linha e depois a segunda (fecha o canto). Esc encerra.',
    'SYMBOL': 'SÍMBOLO: escolha na lista à esquerda e clique para inserir (vários). Digite R + Enter para girar 90°. Esc encerra.',
    'SHEETPOS': 'FOLHA: clique onde o canto inferior esquerdo da folha deve ficar (a folha cresce para a direita e para cima).',
    'UNIPOS': 'UNIFILAR: clique onde o canto esquerdo do barramento deve ficar (o diagrama cresce para a direita e para baixo).',
    'TABLE': 'TABELA: clique onde o canto superior esquerdo da tabela deve ficar.',
    'DIST': 'DIST: clique dois pontos.',
    'ZOOMW': 'ZOOM JANELA: clique dois cantos.',
    'DIMLINEAR': 'COTA LINEAR: clique o primeiro ponto, o segundo e a posição da cota.',
    'DIMALIGNED': 'COTA ALINHADA: clique o primeiro ponto, o segundo e a posição da cota.'}
SNAP_NAMES = {'end': 'Extremidade', 'mid': 'Ponto médio', 'cen': 'Centro', 'qua': 'Quadrante',
              'int': 'Interseção', 'per': 'Perpendicular'}


def aci_q(c):
    c = abs(c)
    if c == 7 or not 1 <= c <= 255:
        return FG
    r, g, b = colors.aci2rgb(c)
    return QColor(r, g, b)


def wcs(e, x, y):
    """Converte um ponto do sistema próprio do objeto (OCS) para o mundo."""
    try:
        if e.dxf.hasattr('extrusion'):
            v = e.ocs.to_wcs(Vec3(x, y, 0))
            return (v.x, v.y)
    except Exception:
        pass
    return (x, y)


# ---------------------------------------------------------------- objetos desenháveis
class Item:
    """Uma entidade do desenho e sua geometria já achatada (polilinhas) para exibir e consultar."""

    def __init__(self, e, dist):
        self.e, self.dist = e, dist
        self.rebuild()

    def rebuild(self):
        self.polys, self.texts, self._segs, self._snaps = [], [], None, None
        try:
            self._build(self.e, 0)
        except Exception:
            pass
        xs, ys = [], []
        for pl in self.polys:
            for i in range(pl.size()):
                xs.append(pl[i].x())
                ys.append(pl[i].y())
        for x, y, h, s, _ in self.texts:
            xs += [x, x + max(len(s), 1) * h * .6]
            ys += [y, y + h]
        self.bbox = (min(xs), min(ys), max(xs), max(ys)) if xs else None

    def _build(self, e, depth):
        t, d = e.dxftype(), e.dxf
        if t in ('TEXT', 'ATTRIB'):
            self.texts.append((d.insert.x, d.insert.y, d.get('height', 1) or 1, d.get('text', ''), d.get('rotation', 0) or 0))
        elif t == 'MTEXT':
            self.texts.append((d.insert.x, d.insert.y, d.get('char_height', 1) or 1,
                               e.plain_text().replace('\n', ' '), d.get('rotation', 0) or 0))
        elif t in ('INSERT', 'DIMENSION', 'LEADER', 'MLEADER'):
            if depth < 6:
                try:
                    for v in e.virtual_entities():
                        self._build(v, depth + 1)
                except Exception:
                    pass
        else:
            try:
                path = ezpath.make_path(e)
            except Exception:
                return
            for sp in path.sub_paths():
                # no máximo 20 mil pontos por trecho e ignora coordenadas absurdas (comuns em DWG com lixo)
                pts = [(v.x, v.y) for v in islice(sp.flattening(self.dist), 20000)]
                pts = [q for q in pts if abs(q[0]) < 1e12 and abs(q[1]) < 1e12]
                if len(pts) > 1:
                    self.polys.append(QPolygonF([QPointF(*q) for q in pts]))

    def segments(self):
        if self._segs is None:
            s = []
            for pl in self.polys:
                for i in range(pl.size() - 1):
                    s.append(((pl[i].x(), pl[i].y()), (pl[i + 1].x(), pl[i + 1].y())))
            self._segs = s
        return self._segs

    def snap_points(self):
        """Lista de ((x, y), tipo) com tipo end/mid/cen/qua."""
        if self._snaps is None:
            e, t, out = self.e, self.e.dxftype(), []
            try:
                if t == 'LINE':
                    a, b = e.dxf.start, e.dxf.end
                    out = [((a.x, a.y), 'end'), ((b.x, b.y), 'end'), (((a.x + b.x) / 2, (a.y + b.y) / 2), 'mid')]
                elif t == 'CIRCLE':
                    c, r = e.dxf.center, e.dxf.radius
                    out = [(wcs(e, c.x, c.y), 'cen')]
                    out += [(wcs(e, c.x + r * math.cos(k * math.pi / 2), c.y + r * math.sin(k * math.pi / 2)), 'qua')
                            for k in range(4)]
                elif t == 'ARC':
                    c, r = e.dxf.center, e.dxf.radius
                    s, en = e.dxf.start_angle, e.dxf.end_angle
                    sw = (en - s) % 360 or 360
                    pt = lambda ang: wcs(e, c.x + r * math.cos(math.radians(ang)), c.y + r * math.sin(math.radians(ang)))
                    out = [(wcs(e, c.x, c.y), 'cen'), (pt(s), 'end'), (pt(en), 'end'), (pt(s + sw / 2), 'mid')]
                elif t == 'LWPOLYLINE':
                    P = [(p[0], p[1], p[2]) for p in e.get_points('xyb')]
                    n = len(P)
                    out = [(wcs(e, x, y), 'end') for x, y, _ in P]
                    for i in range(n if e.closed else n - 1):
                        (x1, y1, b1), (x2, y2, _) = P[i], P[(i + 1) % n]
                        if not b1:
                            out.append((wcs(e, (x1 + x2) / 2, (y1 + y2) / 2), 'mid'))
                elif t == 'INSERT':
                    i = e.dxf.insert
                    out = [((i.x, i.y), 'end')]
                else:
                    for pl in self.polys:
                        if pl.size():
                            out.append(((pl[0].x(), pl[0].y()), 'end'))
                            out.append(((pl[pl.size() - 1].x(), pl[pl.size() - 1].y()), 'end'))
            except Exception:
                out = []
            self._snaps = out
        return self._snaps

    def hit(self, p, tol):
        b = self.bbox
        if b is None or not (b[0] - tol <= p[0] <= b[2] + tol and b[1] - tol <= p[1] <= b[3] + tol):
            return False
        for a, c in self.segments():
            if geom.seg_point_dist(p, a, c) <= tol:
                return True
        return any(x <= p[0] <= x + max(len(s), 1) * h * .6 and y <= p[1] <= y + h for x, y, h, s, _ in self.texts)


# ---------------------------------------------------------------- área de desenho
class Canvas(QWidget):
    def __init__(self, win):
        super().__init__()
        self.w = win
        self.z, self.ox, self.oy = 20.0, -5.0, -5.0
        self.mouse = (0.0, 0.0)            # posição do mouse em pixels
        self.cur = ((0.0, 0.0), None)      # (ponto do desenho já com snap/orto/polar, tipo de snap)
        self.pan = self.d0 = self.d1 = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.CrossCursor)

    # conversões entre tela (pixels) e desenho
    def tr(self):
        return QTransform(self.z, 0, 0, -self.z, -self.ox * self.z, self.height() + self.oy * self.z)

    def to_w(self, sx, sy):
        return (sx / self.z + self.ox, (self.height() - sy) / self.z + self.oy)

    def to_s(self, x, y):
        return ((x - self.ox) * self.z, self.height() - (y - self.oy) * self.z)

    def refresh_cursor(self):
        w = self.w
        p, kind = w.snap_at(self.to_w(*self.mouse), 12 / self.z)
        if kind is None and w.pts and w.cmd in DRAW_REL and not w.selphase:
            o = w.pts[-1]
            if w.ortho:
                p = geom.ortho_point(o, p)
            elif w.polar:
                p = geom.polar_point(o, p, w.polar_inc)
        self.cur = (p, kind)
        return p

    def zoom_to(self, x0, y0, x1, y1):
        wd, ht = max(abs(x1 - x0), 1e-9), max(abs(y1 - y0), 1e-9)
        self.z = max(1e-9, min(self.width() / wd, self.height() / ht) * .95)
        self.ox = (x0 + x1) / 2 - self.width() / 2 / self.z
        self.oy = (y0 + y1) / 2 - self.height() / 2 / self.z
        self.refresh_cursor()
        self.update()

    def fit(self):
        lc = self.w.layer_info()
        xs0 = ys0 = 1e300
        xs1 = ys1 = -1e300
        for it in self.w.items:
            b = it.bbox
            if b is None or not lc.get(it.e.dxf.layer, DEFAULT_LC)[0]:
                continue
            xs0, ys0, xs1, ys1 = min(xs0, b[0]), min(ys0, b[1]), max(xs1, b[2]), max(ys1, b[3])
        if xs0 > xs1:
            xs0, ys0, xs1, ys1 = -10, -10, 10, 10
        self.zoom_to(xs0, ys0, xs1, ys1)

    # ----- desenho
    def paintEvent(self, _):
        p, w = QPainter(self), self.w
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), BG)
        p.setTransform(self.tr())
        x0, y1 = self.to_w(0, 0)
        x1, y0 = self.to_w(self.width(), self.height())
        if w.grid:
            self.draw_grid(p, x0, y0, x1, y1)
        self.draw_scene(p, x0, y0, x1, y1, self.z, self.ox, self.oy, 3.78 if w.show_lw else None, False)
        # pré-visualização do comando em andamento
        pen = QPen(ACC, 1, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        p.setPen(pen)
        m, kind = self.cur
        self.draw_preview(p, m)
        # marcador, snap e medida sobre a tela
        p.resetTransform()
        sx, sy = self.to_s(*m)
        if kind:
            self.draw_marker(p, sx, sy, kind)
        else:
            p.setPen(QPen(ACC, 1))
            p.drawRect(QRectF(sx - 4, sy - 4, 8, 8))
        if w.pts and w.cmd in DRAW_REL and not w.selphase:
            o = w.pts[-1]
            ang = math.degrees(math.atan2(m[1] - o[1], m[0] - o[0]))
            p.setPen(QPen(ACC, 1))
            p.drawText(QPointF(sx + 14, sy + 24), f'{geom.dist(o, m):.3f}  <  {ang:.1f}°')
        if self.d0 is not None and self.d1 is not None:
            p.setPen(QPen(QColor(120, 180, 255), 1, Qt.PenStyle.DashLine))
            p.drawRect(QRectF(QPointF(*self.d0), QPointF(*self.d1)).normalized())
        p.end()

    def draw_grid(self, p, x0, y0, x1, y1):
        step = 10 ** math.ceil(math.log10(14 / self.z))     # pontos a 14 a 140 pixels de distância
        nx, ny = (x1 - x0) / step, (y1 - y0) / step
        if nx * ny > 20000 or nx < 1 or ny < 1:
            return
        pen = QPen(QColor(205, 210, 220) if LIGHT else QColor(55, 63, 76), 2)
        pen.setCosmetic(True)
        p.setPen(pen)
        gx = math.floor(x0 / step) * step
        while gx <= x1:
            gy = math.floor(y0 / step) * step
            while gy <= y1:
                p.drawPoint(QPointF(gx, gy))
                gy += step
            gx += step

    def draw_scene(self, p, x0, y0, x1, y1, z, ox, oy, pxmm, plot):
        """Desenha os objetos visíveis na janela (x0,y0)-(x1,y1) do desenho. Serve para a tela e para o PDF."""
        w = self.w
        lc = w.layer_info()
        font = QFont()
        font.setPixelSize(10)
        p.setFont(font)
        for it in w.items:
            b = it.bbox
            if b is None or b[2] < x0 or b[0] > x1 or b[3] < y0 or b[1] > y1:
                continue
            try:
                e = it.e
                if not lc.get(e.dxf.layer, DEFAULT_LC)[0]:
                    continue
                sel = (not plot) and it in w.sel
                lt, mm = w.style_of(e, lc)
                wpx = estilo.pen_width_px(mm, pxmm)
                if sel:
                    pen = QPen(ACC, max(2, wpx), Qt.PenStyle.DashLine)
                else:
                    col = adapt_color(w.ecolor(e, lc), plot)
                    pen = QPen(col, wpx)
                    pat = estilo.scaled_pattern(lt, wpx)
                    if pat:
                        pen.setDashPattern(pat)
                pen.setCosmetic(True)
                p.setPen(pen)
                if max(abs(b[0] - ox), abs(b[2] - ox), abs(b[1] - oy), abs(b[3] - oy)) * z > 5e6:
                    # objeto muito maior que a tela: recorta na janela para não passar números gigantes ao Qt
                    mx, my = (x1 - x0) * .1, (y1 - y0) * .1
                    for a_, c_ in it.segments():
                        r = geom.clip_segment(a_, c_, x0 - mx, y0 - my, x1 + mx, y1 + my)
                        if r:
                            p.drawLine(QPointF(*r[0]), QPointF(*r[1]))
                else:
                    for pl in it.polys:
                        p.drawPolyline(pl)
                for x, y, h, s, rot in it.texts:
                    if h * z >= 3 and x0 - len(s) * h <= x <= x1 and y0 - h <= y <= y1 + h:
                        p.save()
                        p.translate(x, y)
                        p.rotate(rot)
                        p.scale(h / 10, -h / 10)
                        p.drawText(0, 0, s)
                        p.restore()
            except Exception:
                continue

    def draw_symbol_preview(self, p, m):
        w = self.w
        sid = w.st.get('sid')
        if not sid:
            return
        k, rot = w.sym_scale, w.st.get('rot', 0)
        p.save()
        p.translate(m[0], m[1])
        p.rotate(rot)
        p.scale(k, k)
        pen = QPen(ACC, 1)
        pen.setCosmetic(True)
        p.setPen(pen)
        for pr in E.SYMBOLS[sid]['prims']:
            kind = pr[0]
            if kind == 'line':
                p.drawLine(QPointF(*pr[1]), QPointF(*pr[2]))
            elif kind == 'circle':
                p.drawEllipse(QPointF(*pr[1]), pr[2], pr[2])
            elif kind == 'poly':
                pts = [QPointF(*a) for a in pr[1]]
                p.drawPolygon(QPolygonF(pts)) if pr[2] else p.drawPolyline(QPolygonF(pts))
            elif kind == 'text':
                txt, (tx, ty), th = pr[1], pr[2], pr[3]
                ox_, oy_ = E.text_origin(txt, tx, ty, th)
                p.save()
                p.translate(ox_, oy_)
                p.scale(th / 10, -th / 10)
                f2 = QFont()
                f2.setPixelSize(10)
                p.setFont(f2)
                p.drawText(0, 0, txt)
                p.restore()
        p.restore()

    def draw_preview(self, p, m):
        w, c, q = self.w, self.w.cmd, self.w.pts
        if c == 'SYMBOL':
            return self.draw_symbol_preview(p, m)
        if not q or w.selphase:
            return
        P = lambda pts: QPolygonF([QPointF(*a) for a in pts])
        if c in ('LINE', 'PLINE', 'DIMLINEAR', 'DIMALIGNED'):
            p.drawPolyline(P(q + [m]))
        elif c == 'RECT':
            a = q[0]
            p.drawPolygon(P([a, (m[0], a[1]), m, (a[0], m[1])]))
        elif c == 'CIRCLE':
            r = geom.dist(q[0], m)
            p.drawEllipse(QPointF(*q[0]), r, r)
        elif c == 'ARC':
            res = geom.arc_from_3pts(q[0], q[1], m) if len(q) == 2 else None
            p.drawPolyline(P(geom.arc_points(*res)) if res else P(q + [m]))
        elif c in ('MOVE', 'COPY', 'ROTATE', 'MIRROR', 'DIST', 'SCALE'):
            p.drawLine(QPointF(*q[0]), QPointF(*m))
        elif c == 'ZOOMW':
            a = q[0]
            p.drawPolygon(P([a, (m[0], a[1]), m, (a[0], m[1])]))

    @staticmethod
    def draw_marker(p, sx, sy, kind):
        p.setPen(QPen(GUIDE, 2))
        r = 6
        if kind == 'end':
            p.drawRect(QRectF(sx - r, sy - r, 2 * r, 2 * r))
        elif kind == 'mid':
            p.drawPolygon(QPolygonF([QPointF(sx, sy - r), QPointF(sx - r, sy + r), QPointF(sx + r, sy + r)]))
        elif kind == 'cen':
            p.drawEllipse(QPointF(sx, sy), r, r)
        elif kind == 'qua':
            p.drawPolygon(QPolygonF([QPointF(sx, sy - r), QPointF(sx + r, sy), QPointF(sx, sy + r), QPointF(sx - r, sy)]))
        elif kind == 'int':
            p.drawLine(QPointF(sx - r, sy - r), QPointF(sx + r, sy + r))
            p.drawLine(QPointF(sx - r, sy + r), QPointF(sx + r, sy - r))
        elif kind == 'per':
            p.drawPolyline(QPolygonF([QPointF(sx - r, sy - r), QPointF(sx - r, sy + r), QPointF(sx + r, sy + r)]))
        p.drawText(QPointF(sx + r + 4, sy - r - 2), SNAP_NAMES.get(kind, ''))

    # ----- mouse e teclado
    def mousePressEvent(self, ev):
        sx, sy = ev.position().x(), ev.position().y()
        self.mouse = (sx, sy)
        alt = bool(ev.modifiers() & Qt.KeyboardModifier.AltModifier)
        b = ev.button()
        if b == Qt.MouseButton.MiddleButton or (b == Qt.MouseButton.LeftButton and alt):
            self.pan = (sx, sy, self.ox, self.oy)  # Option + arrastar faz pan no trackpad do Mac
        elif b == Qt.MouseButton.RightButton:       # como no AutoCAD: botão direito = Enter (ou repete o último comando)
            if self.w.cmd or self.w.selphase:
                self.w.enter()
            elif self.w.last_cmd:
                self.w.begin(self.w.last_cmd)
        elif b == Qt.MouseButton.LeftButton:
            if self.w.cmd and not self.w.selphase:
                self.w.point(self.refresh_cursor())
            else:
                self.d0, self.d1 = (sx, sy), None

    def mouseMoveEvent(self, ev):
        sx, sy = ev.position().x(), ev.position().y()
        self.mouse = (sx, sy)
        if self.pan:
            self.ox = self.pan[2] - (sx - self.pan[0]) / self.z
            self.oy = self.pan[3] + (sy - self.pan[1]) / self.z
        if self.d0 is not None:
            self.d1 = (sx, sy)
        m = self.refresh_cursor()
        self.w.coords.setText(f'{m[0]:.3f}, {m[1]:.3f}')
        self.update()

    def mouseReleaseEvent(self, ev):
        self.pan = None
        if ev.button() == Qt.MouseButton.LeftButton and self.d0 is not None:
            a, b = self.d0, (ev.position().x(), ev.position().y())
            add = bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            if abs(a[0] - b[0]) < 4 and abs(a[1] - b[1]) < 4:
                self.w.pick(self.to_w(*b), 8 / self.z, add)
            else:
                wa, wb = self.to_w(*a), self.to_w(*b)
                self.w.window_select((min(wa[0], wb[0]), min(wa[1], wb[1]), max(wa[0], wb[0]), max(wa[1], wb[1])),
                                     b[0] >= a[0], add)
        self.d0 = self.d1 = None
        self.update()

    def wheelEvent(self, ev):
        dy = ev.angleDelta().y()
        if dy == 0:
            return
        sx, sy = ev.position().x(), ev.position().y()
        wx, wy = self.to_w(sx, sy)
        self.z = max(1e-9, min(self.z * math.pow(1.0016, dy), 1e9))
        self.ox, self.oy = wx - sx / self.z, wy - (self.height() - sy) / self.z
        self.refresh_cursor()
        self.update()

    def keyPressEvent(self, ev):
        k = ev.key()
        if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if self.w.cmd or self.w.selphase:
                self.w.enter()
            elif self.w.last_cmd:
                self.w.begin(self.w.last_cmd)   # Enter/Espaço repete o último comando
        elif k == Qt.Key.Key_Escape:
            self.w.cancel()
        elif k in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):  # no Mac a tecla "delete" é Backspace
            self.w.begin('ERASE')
        elif ev.text() and ev.text().isprintable():
            self.w.cmd_edit.setFocus()
            self.w.cmd_edit.setText(self.w.cmd_edit.text() + ev.text())


# ---------------------------------------------------------------- janela principal
class QuadroDialog(QDialog):
    """Quadro de cargas: o usuário digita os circuitos; o programa sugere seção do cabo e disjuntor (NBR 5410, tab. 36, B1)."""
    COLS = ['Descrição', 'Tipo', 'Tensão (V)', 'Fases', 'Potência (VA)']

    def __init__(self, parent, circuits, fd):
        super().__init__(parent)
        self.setWindowTitle('Quadro de cargas')
        self.resize(1050, 680)
        self.q, self.insert = None, False
        lay = QVBoxLayout(self)
        info = QLabel('Digite os circuitos e clique em Calcular. A seção do condutor (cobre, PVC, eletroduto embutido, '
                      '30 °C, método B1 da NBR 5410) e o disjuntor são SUGESTÕES: confira com a norma e com o seu projeto. '
                      'Não inclui queda de tensão nem agrupamento de circuitos.')
        info.setWordWrap(True)
        lay.addWidget(info)
        self.tin = QTableWidget(0, 5)
        self.tin.setHorizontalHeaderLabels(self.COLS)
        self.tin.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.tin, 3)
        row = QHBoxLayout()
        for text, fn in (('Adicionar circuito', lambda: self.add_row()), ('Remover circuito', self.del_row)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, fn=fn: fn())
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(QLabel('Fator de demanda (0 a 1):'))
        self.fd = QLineEdit(E.fmt(fd, 2))
        self.fd.setMaximumWidth(70)
        row.addWidget(self.fd)
        lay.addLayout(row)
        self.tout = QTableWidget(0, len(E.HEADER))
        self.tout.setHorizontalHeaderLabels(E.HEADER)
        self.tout.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tout.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.tout, 4)
        self.note = QLabel('')
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        row2 = QHBoxLayout()
        for text, fn in (('Calcular', self.calc), ('Salvar CSV (Excel)…', self.save_csv),
                         ('Inserir no desenho', self.do_insert), ('Fechar', self.reject)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, fn=fn: fn())
            row2.addWidget(b)
        lay.addLayout(row2)
        for c in (circuits or [{'nome': 'Iluminação social', 'tipo': 'Iluminação', 'v': 127, 'fases': 'F+N', 'va': 600},
                               {'nome': 'Tomadas sala', 'tipo': 'TUG', 'v': 127, 'fases': 'F+N', 'va': 1500},
                               {'nome': 'Chuveiro', 'tipo': 'TUE', 'v': 220, 'fases': 'F+F', 'va': 5500}]):
            self.add_row(c)

    def add_row(self, c=None):
        c = c or {'nome': '', 'tipo': 'TUG', 'v': 127, 'fases': 'F+N', 'va': ''}
        r = self.tin.rowCount()
        self.tin.insertRow(r)
        self.tin.setItem(r, 0, QTableWidgetItem(str(c['nome'])))
        for col, opts, val in ((1, E.TIPOS, c['tipo']), (3, E.FASES, c['fases'])):
            cb = QComboBox()
            cb.addItems(list(opts))
            cb.setCurrentText(val)
            self.tin.setCellWidget(r, col, cb)
        self.tin.setItem(r, 2, QTableWidgetItem(E.fmt(float(c['v']), 0)))
        self.tin.setItem(r, 4, QTableWidgetItem(E.fmt(float(c['va']), 0) if c['va'] != '' else ''))

    def del_row(self):
        r = self.tin.currentRow()
        if r >= 0:
            self.tin.removeRow(r)

    def read(self):
        """Lista de circuitos ou None se algum número estiver errado."""
        out = []
        for r in range(self.tin.rowCount()):
            g = lambda col: (self.tin.item(r, col).text() if self.tin.item(r, col) else '')
            v, va = Main.num(g(2)), Main.num(g(4))
            if v is None or va is None or v <= 0 or va <= 0:
                self.note.setText(f'Confira a linha {r + 1}: tensão e potência precisam ser números maiores que zero.')
                return None
            out.append({'num': r + 1, 'nome': g(0) or f'Circuito {r + 1}', 'tipo': self.tin.cellWidget(r, 1).currentText(),
                        'v': v, 'fases': self.tin.cellWidget(r, 3).currentText(), 'va': va})
        if not out:
            self.note.setText('Adicione pelo menos um circuito.')
            return None
        return out

    def fd_value(self):
        v = Main.num(self.fd.text())
        return v if v is not None and 0 < v <= 1 else 1.0

    def calc(self):
        ck = self.read()
        if ck is None:
            return False
        q = E.quadro(ck, self.fd_value())
        self.q = q
        rows = q['rows'] + q['footer']
        self.tout.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for j, t in enumerate(r):
                self.tout.setItem(i, j, QTableWidgetItem(t))
        warns = [f'Circuito {c["num"]}: {d["aviso"]}' for c, d in zip(ck, q['res']) if d['aviso']]
        self.note.setText('  '.join(warns) if warns else 'Cálculo pronto. Confira os valores antes de usar.')
        return True

    def save_csv(self):
        if not self.calc():
            return
        p, _ = QFileDialog.getSaveFileName(self, 'Salvar quadro de cargas', 'quadro_de_cargas.csv', 'CSV (*.csv)')
        if p:
            with open(p, 'w', encoding='utf-8-sig', newline='') as fh:
                fh.write(E.to_csv(self.q['header'], self.q['rows'], self.q['footer']))
            self.note.setText(f'Salvo em {p}')

    def do_insert(self):
        if self.calc():
            self.insert = True
            self.accept()


class Main(QMainWindow):
    ODA_MAC = '/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter'

    def __init__(self):
        super().__init__()
        self.setWindowTitle('ElectraCad')
        self.resize(1280, 820)
        self.setAcceptDrops(True)
        self.cfg = QSettings('ElectraCad', 'app')
        self.apply_oda(self.cfg.value('oda', '') or self.find_oda())
        self.items, self.sel, self.pts, self.hist, self._op = [], set(), [], [], []
        self.cmd = self.last_cmd = None
        self.show_lw, self.sym_scale, self.circuits, self.fd = True, 12.0, [], 1.0
        self.unit_mm, self.grid, self.focus, self.sheet_cfg = 10.0, False, False, {}
        self.selphase, self.st = False, {}
        self.snap_on, self.ortho, self.polar, self.polar_inc = True, False, False, 15.0
        self.path, self.suggest, self.cur, self.dirty, self.text_h, self.dist = None, 'desenho', '0', False, None, 0.01
        # o desenho precisa existir antes de qualquer botão ser criado: ligar ORTO/SNAP já consulta as camadas
        self.doc = ezdxf.new('R2018', setup=True)
        self.msp = self.doc.modelspace()
        self.cv = Canvas(self)

        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.msg, self.cmd_edit, self.coords = QLabel(), QLineEdit(), QLabel('0, 0')
        self.msg.setStyleSheet(f'padding:4px 8px;font-weight:600;color:{marca.AZUL};')
        self.cmd_edit.setPlaceholderText('Comando (L, PL, C, M…) ou x,y  @dx,dy  dist<ângulo')
        self.cmd_edit.returnPressed.connect(self.on_cmd)
        lay.addWidget(self.cv, 1)
        row_b = QHBoxLayout()
        row_b.setContentsMargins(0, 0, 6, 2)
        self.msg.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.cmd_edit.setFixedWidth(400)
        row_b.addWidget(self.msg, 1)
        row_b.addWidget(self.cmd_edit)
        lay.addLayout(row_b)
        self.setCentralWidget(box)

        sb = self.statusBar()
        sb.addPermanentWidget(self.coords)
        style = 'QPushButton{padding:2px 10px;}'
        self.b_snap, self.b_ortho, self.b_polar = QPushButton('SNAP'), QPushButton('ORTO'), QPushButton('POLAR')
        for b in (self.b_snap, self.b_ortho, self.b_polar):
            b.setCheckable(True)
            b.setStyleSheet(style)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            sb.addPermanentWidget(b)
        self.b_snap.setToolTip('Atrair para pontos dos objetos (F3)')
        self.b_ortho.setToolTip('Só linhas retas na horizontal/vertical (F8)')
        self.b_polar.setToolTip('Atrai o ângulo para múltiplos de 15° (F10)')
        self.b_snap.toggled.connect(lambda on: self.set_flag('snap_on', on))
        self.b_ortho.toggled.connect(self.toggle_ortho)
        self.b_polar.toggled.connect(self.toggle_polar)
        self.b_snap.setChecked(True)
        self.b_ortho.setChecked(True)   # começa com ORTO ligado: linhas retas por padrão

        dock = QDockWidget('Camadas', self)
        pn = QWidget()
        pl = QVBoxLayout(pn)
        self.lbl_cur = QLabel()
        self.lw = QListWidget()
        b_new, b_mv = QPushButton('Nova camada'), QPushButton('Seleção → camada atual')
        pl.addWidget(self.lbl_cur)
        pl.addWidget(self.lw)
        pl.addWidget(b_new)
        pl.addWidget(b_mv)
        dock.setWidget(pn)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.lw.itemChanged.connect(self.layer_toggled)
        self.lw.itemClicked.connect(lambda it: self.set_layer(it.text()))
        b_new.clicked.connect(self.new_layer)
        b_mv.clicked.connect(self.sel_to_layer)

        sdock = QDockWidget('Símbolos elétricos', self)
        self.sw = QListWidget()
        self.sw.setIconSize(QSize(30, 30))
        hdr_font = QFont()
        hdr_font.setBold(True)
        for cat in E.CATEGORIAS:
            h = QListWidgetItem(cat.upper())
            h.setFlags(Qt.ItemFlag.NoItemFlags)
            h.setFont(hdr_font)
            self.sw.addItem(h)
            for sid in E.ORDER:
                if E.SYMBOLS[sid]['cat'] == cat:
                    it = QListWidgetItem(QIcon(self.sym_icon(sid)), E.SYMBOLS[sid]['nome'])
                    it.setData(Qt.ItemDataRole.UserRole, sid)
                    self.sw.addItem(it)
        self.sw.itemClicked.connect(lambda it: it.data(Qt.ItemDataRole.UserRole) and self.start_symbol(it.data(Qt.ItemDataRole.UserRole)))
        sdock.setWidget(self.sw)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, sdock)
        self.tabifyDockWidget(dock, sdock)      # Camadas e Símbolos dividem o mesmo espaço (em abas)
        sdock.raise_()
        self.dock_layers, self.dock_symbols = dock, sdock

        self.menus()
        self.toolbars()
        self.load_doc(ezdxf.new('R2018', setup=True), None)

    # ---------- menus e barras
    def menus(self):
        def act(menu, text, fn, key=None):
            a = QAction(text, self)
            a.triggered.connect(lambda _=False: fn())
            if key:
                a.setShortcut(QKeySequence(key))
            menu.addAction(a)
        f, e, v, el, c = (self.menuBar().addMenu(n) for n in ('Arquivo', 'Editar', 'Exibir', 'Elétrica', 'Configurar'))
        act(f, 'Novo', self.new_doc, 'Ctrl+N')
        act(f, 'Abrir (DXF/DWG)…', self.open_dialog, 'Ctrl+O')
        act(f, 'Salvar', self.save, 'Ctrl+S')
        act(f, 'Salvar como (DXF/DWG)…', lambda: self.save(True), 'Ctrl+Shift+S')
        act(f, 'Importar projeto (JSON da IA)…', self.import_project)
        act(f, 'Exportar projeto (JSON)…', self.export_project)
        self.m_recent = f.addMenu('Abrir recente')
        self.m_recent.aboutToShow.connect(self.fill_recent)
        act(f, 'Exportar PDF…', self.export_pdf, 'Ctrl+P')
        act(el, 'Criar camadas elétricas padrão', self.elec_layers)
        act(el, 'Eletroduto no teto (linha contínua)', self.conduit_teto)
        act(el, 'Eletroduto no piso (tracejado)', self.conduit_piso)
        act(el, 'Contar símbolos do desenho…', self.count_symbols)
        act(el, 'Inserir legenda no desenho', self.legend)
        act(el, 'Quadro de cargas…', self.qcargas)
        act(el, 'Lista de materiais (CSV)…', self.export_bom)
        act(el, 'Inserir folha com carimbo…', self.sheet_dialog)
        act(el, 'Diagrama unifilar (do quadro de cargas)', self.start_unifilar)
        act(el, 'Lista de cabos (CSV)…', self.export_cables)
        act(v, 'Mostrar espessuras de linha', self.toggle_lw)
        act(v, 'Alternar fundo claro/escuro', self.toggle_theme)
        act(v, 'Tela limpa (esconde barras e painéis)', self.toggle_focus, 'Ctrl+Shift+F')
        act(v, 'Grade de pontos', self.toggle_grid, 'F7')
        act(self.menuBar().addMenu('Ajuda'), 'Sobre o ElectraCad', self.about)
        act(e, 'Desfazer', self.undo, 'Ctrl+Z')
        act(e, 'Selecionar tudo', self.select_all, 'Ctrl+A')
        act(v, 'Zoom total', self.cv.fit)
        act(v, 'Zoom janela', lambda: self.begin('ZOOMW'))
        act(e, 'Liga/desliga SNAP', self.b_snap.toggle, 'F3')
        act(e, 'Liga/desliga ORTO', self.b_ortho.toggle, 'F8')
        act(e, 'Liga/desliga POLAR', self.b_polar.toggle, 'F10')
        act(c, 'ODA File Converter (opcional, só para salvar DWG moderno)…', self.ask_oda)
        act(c, 'Altura do texto…', self.ask_text_h)
        act(c, 'Tamanho dos símbolos…', self.ask_sym_scale)
        act(c, 'Incremento do POLAR…', self.ask_polar)

    def toolbars(self):
        """Uma única barra fina (as outras ferramentas ficam em menus suspensos): mais área para o desenho."""
        tb = QToolBar('Ferramentas', self)
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.tool_bar = tb

        def quick(text, cmd, alias):
            a = QAction(text, self)
            a.setToolTip(f'{text} ({alias})')
            a.triggered.connect(lambda _=False, c=cmd: self.begin(c))
            tb.addAction(a)

        def menu_btn(title, items):
            btn = QToolButton()
            btn.setText(title + ' ▾')
            m = QMenu(btn)
            for text, cmd, alias in items:
                a = m.addAction(f'{text}   ({alias})')
                a.triggered.connect(lambda _=False, c=cmd: self.begin(c))
            btn.setMenu(m)
            btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            tb.addWidget(btn)
        for t, c, a in (('Linha', 'LINE', 'L'), ('Polilinha', 'PLINE', 'PL'), ('Retângulo', 'RECT', 'REC'),
                        ('Círculo', 'CIRCLE', 'C'), ('Texto', 'TEXT', 'T')):
            quick(t, c, a)
        tb.addSeparator()
        for t, c, a in (('Mover', 'MOVE', 'M'), ('Copiar', 'COPY', 'CO'), ('Apagar', 'ERASE', 'E'), ('Desfazer', 'UNDO', 'U')):
            quick(t, c, a)
        tb.addSeparator()
        menu_btn('Desenhar', [('Arco', 'ARC', 'A'), ('Cota linear', 'DIMLINEAR', 'DLI'),
                              ('Cota alinhada', 'DIMALIGNED', 'DAL'), ('Medir distância', 'DIST', 'DI')])
        menu_btn('Editar', [('Girar', 'ROTATE', 'RO'), ('Escalar', 'SCALE', 'SC'), ('Espelhar', 'MIRROR', 'MI'),
                            ('Deslocar', 'OFFSET', 'O'), ('Aparar', 'TRIM', 'TR'), ('Estender', 'EXTEND', 'EX'),
                            ('Canto', 'FILLET', 'F'), ('Explodir', 'EXPLODE', 'X')])
        menu_btn('Elétrica', [('Eletroduto no teto', 'CONDUIT_T', 'ET'), ('Eletroduto no piso', 'CONDUIT_P', 'EP'),
                              ('Contar símbolos', 'COUNT', 'CONTAR'), ('Inserir legenda', 'LEGEND', 'LEGENDA'),
                              ('Quadro de cargas', 'QCARGAS', 'QC'), ('Lista de materiais (CSV)', 'BOM', 'LM'),
                              ('Folha com carimbo', 'SHEET', 'FOLHA'), ('Diagrama unifilar', 'UNIFILAR', 'UNI'),
                              ('Lista de cabos (CSV)', 'CABOS', 'CABOS'), ('Exportar PDF', 'PDF', 'PDF')])
        tb.addSeparator()
        quick('Tela limpa', 'FOCUS', 'FOCO')
        self.addToolBar(tb)

    def set_flag(self, name, on):
        setattr(self, name, on)
        self.cv.refresh_cursor()
        self.cv.update()

    def toggle_ortho(self, on):
        self.ortho = on
        if on and self.b_polar.isChecked():
            self.b_polar.setChecked(False)
        self.cv.refresh_cursor()
        self.cv.update()

    def toggle_polar(self, on):
        self.polar = on
        if on and self.b_ortho.isChecked():
            self.b_ortho.setChecked(False)
        self.cv.refresh_cursor()
        self.cv.update()

    def update_title(self):
        name = os.path.basename(self.path) if self.path else 'Sem título'
        self.setWindowTitle(f'ElectraCad — {name}{" *" if self.dirty else ""}')

    # ---------- configuração do ODA (DWG)
    def find_oda(self):
        return self.ODA_MAC if os.path.exists(self.ODA_MAC) else ''

    def apply_oda(self, path):
        if not path:
            return
        if path.rstrip('/').endswith('.app'):
            path = path.rstrip('/') + '/Contents/MacOS/ODAFileConverter'
        key = 'win_exec_path' if sys.platform.startswith('win') else 'unix_exec_path'
        ezdxf.options.set('odafc-addon', key, path)

    def ask_oda(self):
        p, _ = QFileDialog.getOpenFileName(self, 'Selecione o ODAFileConverter (.app)', '/Applications')
        if p:
            self.cfg.setValue('oda', p)
            self.apply_oda(p)

    def ask_text_h(self):
        v, ok = QInputDialog.getDouble(self, 'Altura do texto', 'Altura (unidades do desenho):',
                                       self.text_height(), 0.001, 1e9, 3)
        if ok:
            self.text_h = v

    def ask_polar(self):
        v, ok = QInputDialog.getDouble(self, 'POLAR', 'Incremento em graus:', self.polar_inc, 1, 90, 1)
        if ok:
            self.polar_inc = v

    # ---------- arquivos
    def new_doc(self):
        if self.confirm_discard():
            self.load_doc(ezdxf.new('R2018', setup=True), None)

    def open_dialog(self):
        p, _ = QFileDialog.getOpenFileName(self, 'Abrir', '', 'Desenhos CAD (*.dxf *.dwg)')
        if p:
            self.open_path(p)

    def open_path(self, p):
        if not self.confirm_discard():
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            if p.lower().endswith('.dwg'):
                doc, path = self.read_dwg(p), None
                if doc is None:
                    return
            else:
                try:
                    doc = ezdxf.readfile(p)
                except ezdxf.DXFStructureError:
                    doc, _aud = recover.readfile(p)
                path = p
            self.suggest = os.path.splitext(os.path.basename(p))[0]
            self.add_recent(p)
            self.load_doc(doc, path)
            self.say(f'{len(self.items)} objetos carregados.')
        except Exception as ex:
            txt = log_exc('(erro ao abrir)')
            QApplication.restoreOverrideCursor()
            alert(self, 'Erro ao abrir', f'Não foi possível abrir o arquivo.\n{type(ex).__name__}: {ex}', detail=txt)
        finally:
            QApplication.restoreOverrideCursor()

    def read_dwg(self, p):
        """Abre um DWG: primeiro com o conversor embutido (LibreDWG); se falhar, com o ODA (se instalado)."""
        err = ''
        self.say('Convertendo o DWG… (pode levar alguns segundos)')
        QApplication.processEvents()
        if dwgconv.available():
            try:
                out, _log = dwgconv.dwg_to_dxf(p)
                try:
                    return ezdxf.readfile(out)
                except Exception:
                    return recover.readfile(out)[0]
            except Exception as ex:
                err = str(ex)
                log_exc('(conversão do DWG)')
        if odafc.is_installed():
            return odafc.readfile(p)
        QApplication.restoreOverrideCursor()
        alert(self, 'DWG', 'Não foi possível converter este DWG.\n\n' + (err or 'O conversor de DWG não foi encontrado '
              'nesta instalação. Reinstale o ElectraCad.') + '\n\nDica: no AutoCAD/ZWCAD use "Salvar como" DXF e abra o DXF aqui.')
        return None

    def save(self, as_new=False):
        p = self.path
        if as_new or not p:
            p, _ = QFileDialog.getSaveFileName(self, 'Salvar', self.suggest, 'DXF (*.dxf);;DWG (*.dwg)')
            if not p:
                return False
        try:
            if p.lower().endswith('.dwg'):
                if odafc.is_installed():
                    odafc.export_dwg(self.doc, p, replace=True)
                elif dwgconv.can_write():
                    if alert(self, 'Salvar DWG', 'O ElectraCad grava DWG no formato R2000: abre no AutoCAD e no ZWCAD, '
                             'mas detalhes de versões mais novas podem se perder. Guarde também uma cópia em DXF.',
                             buttons=('Salvar DWG', 'Cancelar')) != 0:
                        return False
                    import tempfile
                    tmp = os.path.join(tempfile.mkdtemp(prefix='electracad_'), 'tmp.dxf')
                    self.doc.saveas(tmp)
                    dwgconv.dxf_to_dwg(tmp, p)
                else:
                    alert(self, 'DWG', 'O gravador de DWG não foi encontrado. Salve em DXF.')
                    return False
            else:
                if not p.lower().endswith('.dxf'):
                    p += '.dxf'
                self.doc.saveas(p)
            self.path, self.dirty = p, False
            self.update_title()
            self.say('Salvo em ' + p)
            return True
        except Exception as ex:
            txt = log_exc('(erro ao salvar)')
            alert(self, 'Erro ao salvar', f'Não foi possível salvar.\n{type(ex).__name__}: {ex}', detail=txt)
            return False

    def confirm_discard(self):
        if not self.dirty:
            return True
        r = alert(self, 'ElectraCad', 'Há alterações não salvas. Deseja salvar?',
                  buttons=('Salvar', 'Descartar', 'Cancelar'), default=0)
        if r == 0:
            return self.save()
        return r == 1   # Cancelar, Esc ou fechar a janela: não continua

    def closeEvent(self, ev):
        ev.accept() if self.confirm_discard() else ev.ignore()

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        urls = ev.mimeData().urls()
        if urls:
            self.open_path(urls[0].toLocalFile())

    def load_doc(self, doc, path):
        self.doc, self.msp, self.path = doc, doc.modelspace(), path
        self.hist, self._op, self.dirty = [], [], False
        try:
            from ezdxf import bbox
            ext = bbox.extents(self.msp, fast=True)
            size = max(ext.size.x, ext.size.y) if ext.has_data else 100
        except Exception:
            size = 100
        self.dist = size / 4000 if math.isfinite(size) and size > 0 else 0.01
        try:
            has = bool(ext.has_data)
        except Exception:
            has = False
        try:
            units = int(doc.header.get('$INSUNITS', 0))
        except Exception:
            units = 0
        # símbolo com ~24 cm de diâmetro: depende da unidade do desenho
        self.sym_scale = {4: 120.0, 5: 12.0, 6: 0.12}.get(units) or (12.0 if not has else max(size / 120, 1e-6))
        self.unit_mm = {1: 25.4, 2: 304.8, 4: 1.0, 5: 10.0, 6: 1000.0}.get(units) or 120.0 / self.sym_scale
        ents = list(self.msp)
        items = []
        self.centralWidget().setEnabled(False)
        try:
            for i, e in enumerate(ents):
                items.append(Item(e, self.dist))
                if i % 400 == 0:
                    self.say(f'Carregando {i}/{len(ents)}…')
                    QApplication.processEvents()
        finally:
            self.centralWidget().setEnabled(True)
        self.items = items
        self.sel.clear()
        self.cur = '0'
        self.fill_layers()
        self.finish_cmd()
        self.update_title()
        self.cv.fit()
        self.cv.setFocus()

    # ---------- histórico (desfazer por operação)
    def end_op(self):
        if self._op:
            self.hist = (self.hist + [self._op])[-300:]
            self.dirty = True
            self.update_title()
        self._op = []

    def do(self, fn):
        """Executa uma operação inteira como uma única ação desfazível."""
        self._op = []
        try:
            return fn()
        finally:
            self.end_op()

    def new_item(self, e):
        it = Item(e, self.dist)
        self.items.append(it)
        return it

    def item_of(self, e):
        return next((i for i in self.items if i.e is e), None)

    def create(self, e):
        self._op.append(('add', e))
        return self.new_item(e)

    def remove(self, it):
        self._op.append(('del', it.e, it.e.copy()))
        self.msp.delete_entity(it.e)
        self.items.remove(it)
        self.sel.discard(it)

    def modify(self, it, fn):
        self._op.append(('mod', it.e, it.e.copy()))
        fn(it.e)
        it.rebuild()

    def replace_refs(self, old, new):
        for op in self.hist + [self._op]:
            for i, rec in enumerate(op):
                if rec[1] is old:
                    op[i] = (rec[0], new) + tuple(rec[2:])

    def undo(self):
        self._op = []
        if not self.hist:
            return self.say('Nada para desfazer.')
        for rec in reversed(self.hist.pop()):
            kind, ref = rec[0], rec[1]
            if kind == 'add':
                it = self.item_of(ref)
                if it:
                    self.items.remove(it)
                try:
                    self.msp.delete_entity(ref)
                except Exception:
                    pass
            else:  # 'del' e 'mod' guardam a cópia original em rec[2]
                if kind == 'mod':
                    it = self.item_of(ref)
                    if it:
                        self.items.remove(it)
                    try:
                        self.msp.delete_entity(ref)
                    except Exception:
                        pass
                cp = rec[2]
                self.msp.add_entity(cp)
                self.new_item(cp)
                self.replace_refs(ref, cp)
        self.sel.clear()
        self.dirty = True
        self.update_title()
        self.say('Desfeito.')
        self.cv.update()

    # ---------- camadas
    def layer_info(self):
        return {l.dxf.name: (l.is_on() and not l.is_frozen(), l.color, l.dxf.get('linetype', 'CONTINUOUS'),
                            l.dxf.get('lineweight', -3)) for l in self.doc.layers}

    def style_of(self, e, lc):
        """(tipo de linha, espessura em mm) efetivos do objeto."""
        try:
            d = e.dxf
            ly = lc.get(d.layer, DEFAULT_LC)
            return (estilo.resolve_linetype(d.get('linetype', 'BYLAYER'), ly[2]),
                    estilo.resolve_lineweight(d.get('lineweight', -1), ly[3]))
        except Exception:
            return 'CONTINUOUS', estilo.DEFAULT_LW_MM

    def fill_layers(self):
        self.lw.blockSignals(True)
        self.lw.clear()
        for l in self.doc.layers:
            it = QListWidgetItem(l.dxf.name)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if l.is_on() else Qt.CheckState.Unchecked)
            pm = QPixmap(12, 12)   # quadradinho com a cor da camada (o texto fica na cor normal, sempre legível)
            pm.fill(aci_q(l.color))
            it.setIcon(QIcon(pm))
            self.lw.addItem(it)
            if l.dxf.name == self.cur:
                self.lw.setCurrentItem(it)
        self.lw.blockSignals(False)
        self.lbl_cur.setText(f'Camada atual: {self.cur}')

    def set_layer(self, name):
        if name in self.doc.layers:
            self.cur = name
            self.lbl_cur.setText(f'Camada atual: {name}')

    def layer_toggled(self, it):
        l = self.doc.layers.get(it.text())
        l.on() if it.checkState() == Qt.CheckState.Checked else l.off()
        self.cv.update()

    def new_layer(self):
        n, ok = QInputDialog.getText(self, 'Nova camada', 'Nome:')
        if ok and n.strip():
            self.make_layer(n.strip())

    def make_layer(self, n):
        if n not in self.doc.layers:
            self.doc.layers.add(n, color=(len(self.doc.layers) % 8) + 1)
        self.cur = n
        self.fill_layers()

    def sel_to_layer(self):
        if not self.sel:
            return self.say('Selecione objetos antes.')

        def f():
            for it in list(self.sel):
                self.modify(it, lambda e: setattr(e.dxf, 'layer', self.cur))
        self.do(f)
        self.say(f'Seleção movida para a camada {self.cur}.')
        self.cv.update()

    def ecolor(self, e, lc):
        d = e.dxf
        if d.get('true_color') is not None:
            r, g, b = colors.int2rgb(d.true_color)
            return QColor(r, g, b)
        c = d.get('color', 256)
        return aci_q(lc.get(d.layer, DEFAULT_LC)[1] if c in (0, 256) else c)

    # ---------- snap e seleção
    def snap_at(self, p, tol):
        """Ponto atraído mais próximo: ((x, y), tipo) ou (p, None)."""
        if not self.snap_on:
            return p, None
        lc = self.layer_info()
        best, kind, bd, segs = None, None, tol, []
        for it in self.items:
            b = it.bbox
            if b is None or p[0] < b[0] - tol or p[0] > b[2] + tol or p[1] < b[1] - tol or p[1] > b[3] + tol:
                continue
            if not lc.get(it.e.dxf.layer, DEFAULT_LC)[0]:
                continue
            for q, k in it.snap_points():
                d = math.hypot(p[0] - q[0], p[1] - q[1])
                if d < bd:
                    best, kind, bd = q, k, d
            if len(segs) < 60:
                segs += [s for s in it.segments() if geom.seg_point_dist(p, s[0], s[1]) <= tol * 2][:60]
        segs = segs[:60]
        for i in range(len(segs)):
            for j in range(i + 1, len(segs)):
                r = geom.seg_intersect(segs[i][0], segs[i][1], segs[j][0], segs[j][1])
                if r:
                    d = math.hypot(p[0] - r[0], p[1] - r[1])
                    if d < bd:
                        best, kind, bd = (r[0], r[1]), 'int', d
        if self.pts and self.cmd in DRAW_REL:
            o = self.pts[-1]
            for s in segs:
                f = geom.foot(o, s[0], s[1])
                if 0 <= f[2] <= 1:
                    d = math.hypot(p[0] - f[0], p[1] - f[1])
                    if d < bd:
                        best, kind, bd = (f[0], f[1]), 'per', d
        return (best, kind) if best else (p, None)

    def item_at(self, p, tol):
        lc = self.layer_info()
        for it in reversed(self.items):
            if lc.get(it.e.dxf.layer, DEFAULT_LC)[0] and it.hit(p, tol):
                return it
        return None

    def pick(self, p, tol, add):
        hit = self.item_at(p, tol)
        if not add and not self.selphase:
            self.sel.clear()
        if hit:
            if add and hit in self.sel:
                self.sel.discard(hit)
            else:
                self.sel.add(hit)
        self.cv.update()

    def window_select(self, r, inside, add):
        if not add:
            self.sel.clear()
        lc = self.layer_info()
        for it in self.items:
            b = it.bbox
            if b is None or not lc.get(it.e.dxf.layer, DEFAULT_LC)[0]:
                continue
            full = b[0] >= r[0] and b[2] <= r[2] and b[1] >= r[1] and b[3] <= r[3]
            touch = not (b[2] < r[0] or b[0] > r[2] or b[3] < r[1] or b[1] > r[3])
            if full or (touch and not inside):
                self.sel.add(it)
        self.cv.update()

    def select_all(self):
        lc = self.layer_info()
        self.sel = {i for i in self.items if lc.get(i.e.dxf.layer, DEFAULT_LC)[0]}
        self.cv.update()

    # ---------- comandos: controle
    def say(self, t):
        self.msg.setText(t)

    def finish_cmd(self, t=''):
        self.cmd, self.pts, self.st, self.selphase = None, [], {}, False
        self.sel.clear()
        self.say(t or 'Pronto. Escolha uma ferramenta ou digite um comando. Enter repete o último.')
        self.cv.refresh_cursor()
        self.cv.update()
        self.cv.setFocus()

    def cancel(self):
        self.finish_cmd('Cancelado.')

    def begin(self, c):
        self.cmd, self.pts, self.st, self.selphase = c, [], {}, False
        if c in ('UNDO', 'ZOOM', 'ORTHO', 'POLAR', 'SNAP'):
            self.cmd = None
            if c == 'UNDO':
                self.undo()
            elif c == 'ZOOM':
                self.cv.fit()
            else:
                {'ORTHO': self.b_ortho, 'POLAR': self.b_polar, 'SNAP': self.b_snap}[c].toggle()
            return
        if c in ACTIONS:
            self.cmd = None
            return getattr(self, ACTIONS[c])()
        self.last_cmd = c
        if c == 'LAYER':
            return self.say('LAYER: digite o nome da camada (cria se não existir) e tecle Enter.')
        if c in SELCMDS:
            if self.sel:
                return self.after_select()
            self.selphase = True
            return self.say(f'{c}: selecione objetos (clique ou arraste uma janela) e tecle Enter.')
        self.say(PROMPT[c])
        self.cv.update()

    def after_select(self):
        c = self.cmd
        self.selphase = False
        if c == 'ERASE':
            self.do(self.erase_sel)
        elif c == 'EXPLODE':
            self.do(self.explode_sel)
        else:
            self.say(PROMPT[c])
            self.cv.update()

    def enter(self):
        if self.selphase:
            if not self.sel:
                return self.finish_cmd('Cancelado: nada selecionado.')
            return self.after_select()
        if self.cmd == 'PLINE' and len(self.pts) > 1:
            self.do(lambda: self.add_pline(self.pts, False))
        self.finish_cmd()

    # ---------- comandos: criação
    def attr(self):
        return {'layer': self.cur}

    def add_line(self, a, b):
        self.create(self.msp.add_line((a[0], a[1]), (b[0], b[1]), dxfattribs=self.attr()))

    def add_pline(self, pts, close):
        self.create(self.msp.add_lwpolyline([(q[0], q[1]) for q in pts], close=close, dxfattribs=self.attr()))

    def add_rect(self, a, b):
        self.create(self.msp.add_lwpolyline([(a[0], a[1]), (b[0], a[1]), (b[0], b[1]), (a[0], b[1])],
                                            close=True, dxfattribs=self.attr()))

    def make_circle(self, r):
        if r > 0:
            c = self.pts[0]
            self.do(lambda: self.create(self.msp.add_circle((c[0], c[1]), r, dxfattribs=self.attr())))
        self.finish_cmd()

    def make_arc(self, p1, p2, p3):
        res = geom.arc_from_3pts(p1, p2, p3)
        if res is None:
            self.pts = []
            return self.say('ARC: os três pontos estão alinhados. Clique de novo o ponto inicial.')
        cx, cy, r, a0, a1 = res
        self.do(lambda: self.create(self.msp.add_arc((cx, cy), r, a0, a1, dxfattribs=self.attr())))
        self.finish_cmd()

    def text_height(self):
        return self.text_h or float(f'{14 / self.cv.z:.3g}')

    def make_text(self, p):
        s, ok = QInputDialog.getText(self, 'Texto', 'Conteúdo:')
        if ok and s:
            h = self.text_height()
            self.do(lambda: self.create(self.msp.add_text(
                s, dxfattribs={**self.attr(), 'insert': (p[0], p[1]), 'height': h})))
        self.finish_cmd()

    def make_dim(self, p1, p2, loc, aligned):
        if geom.dist(p1, p2) < 1e-9:
            return self.finish_cmd('Cota cancelada: os dois pontos são iguais.')
        h = self.text_height()
        style = 'EZDXF' if self.doc.dimstyles.has_entry('EZDXF') else 'Standard'
        ov = {'dimtxt': h, 'dimasz': h, 'dimexe': h * .6, 'dimexo': h * .4, 'dimgap': h * .4, 'dimdec': 2}

        def f():
            if aligned:
                dx, dy = p2[0] - p1[0], p2[1] - p1[1]
                L = math.hypot(dx, dy)
                distance = (loc[0] - p1[0]) * (-dy / L) + (loc[1] - p1[1]) * (dx / L)
                dim = self.msp.add_aligned_dim(p1, p2, distance, dimstyle=style, override=ov, dxfattribs=self.attr())
            else:
                horiz = abs(loc[1] - (p1[1] + p2[1]) / 2) >= abs(loc[0] - (p1[0] + p2[0]) / 2)
                dim = self.msp.add_linear_dim(base=loc, p1=p1, p2=p2, angle=0 if horiz else 90,
                                              dimstyle=style, override=ov, dxfattribs=self.attr())
            dim.render()
            self.create(dim.dimension)
        self.do(f)
        self.finish_cmd('Cota criada.')

    # ---------- elétrica
    @staticmethod
    def sym_icon(sid):
        pm = QPixmap(30, 30)
        pm.fill(QColor(255, 255, 255))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        prims = E.SYMBOLS[sid]['prims']
        x0, y0, x1, y1 = E.extents(prims)
        k = 24 / max(x1 - x0, y1 - y0, 1e-6)
        p.translate(15 - k * (x0 + x1) / 2, 15 + k * (y0 + y1) / 2)
        p.scale(k, -k)
        pen = QPen(FG, 0)
        p.setPen(pen)
        for pr in prims:
            kind = pr[0]
            if kind == 'line':
                p.drawLine(QPointF(*pr[1]), QPointF(*pr[2]))
            elif kind == 'circle':
                p.drawEllipse(QPointF(*pr[1]), pr[2], pr[2])
            elif kind == 'poly':
                pts = QPolygonF([QPointF(*a) for a in pr[1]])
                p.drawPolygon(pts) if pr[2] else p.drawPolyline(pts)
            elif kind == 'text':
                txt, (tx, ty), th = pr[1], pr[2], pr[3]
                ox_, oy_ = E.text_origin(txt, tx, ty, th)
                p.save()
                p.translate(ox_, oy_)
                p.scale(th / 10, -th / 10)
                f2 = QFont()
                f2.setPixelSize(10)
                p.setFont(f2)
                p.drawText(0, 0, txt)
                p.restore()
        p.end()
        return pm

    def start_symbol(self, sid):
        self.begin('SYMBOL')
        self.st['sid'], self.st['rot'] = sid, 0
        self.say(f'{E.SYMBOLS[sid]["nome"]}: clique para inserir (vários). R + Enter gira 90°. Esc encerra.')
        self.cv.setFocus()

    def insert_sym(self, p):
        sid = self.st.get('sid')
        if not sid:
            return self.say('Escolha um símbolo na lista à esquerda.')

        def f():
            self.create(E.insert_symbol(self.doc, self.msp, sid, p, self.sym_scale, self.st.get('rot', 0)))
        known = set(l.dxf.name for l in self.doc.layers)
        self.do(f)
        if E.SYMBOLS[sid]['layer'] not in known:
            self.fill_layers()
        self.cv.update()

    def elec_layers(self):
        made = E.ensure_layers(self.doc)
        self.fill_layers()
        self.say(f'Camadas elétricas criadas: {len(made)}.' if made else 'As camadas elétricas já existem.')

    def conduit(self, name):
        E.ensure_layers(self.doc)
        self.cur = name
        self.fill_layers()
        self.begin('PLINE')
        self.say(f'Camada {name}. ' + PROMPT['PLINE'])

    def conduit_teto(self):
        self.conduit(E.LAYER_ELETRODUTO_TETO)

    def conduit_piso(self):
        self.conduit(E.LAYER_ELETRODUTO_PISO)

    def count_symbols(self):
        rows = E.legend_rows(E.count_symbols(self.msp))
        if not rows:
            return self.say('Nenhum símbolo (bloco) encontrado no desenho.')
        text = '\n'.join(f'{n:>4}  ×  {nome}' for _, nome, n in rows) + f'\n\nTotal: {sum(r[2] for r in rows)}'
        if alert(self, 'Contagem de símbolos', text, buttons=('OK', 'Inserir legenda no desenho')) == 1:
            self.legend()

    def legend(self):
        rows = E.legend_rows(E.count_symbols(self.msp))
        if not rows:
            return self.say('Nenhum símbolo (bloco) encontrado no desenho.')
        table = [['Símbolo', 'Descrição', 'Qtd.']] + [[('sym', sid) if sid else '', nome, str(n)] for sid, nome, n in rows]
        self.start_table(table)

    def start_table(self, table):
        self.begin('TABLE')
        self.st['table'] = table

    def place_table(self, p):
        table = self.st.get('table')
        if not table:
            return self.finish_cmd()
        th = self.text_height()
        rh = th * 2
        cw = E.auto_col_widths(table, th, th * 3)
        E.ensure_layers(self.doc)
        self.do(lambda: [self.create(e) for e in E.draw_table(self.doc, self.msp, p, table, cw, rh, th)])
        self.fill_layers()
        self.finish_cmd('Tabela inserida.')

    def qcargas(self):
        d = QuadroDialog(self, self.circuits, self.fd)
        d.exec()
        ck = d.read() if d.q else None
        if ck:
            self.circuits, self.fd = ck, d.fd_value()
        if d.insert and d.q:
            self.start_table([d.q['header']] + d.q['rows'] + d.q['footer'])

    def toggle_theme(self):
        set_theme(not LIGHT)
        self.cfg.setValue('light', LIGHT)
        self.cv.update()

    def about(self):
        d = QDialog(self)
        d.setWindowTitle('Sobre o ElectraCad')
        lay = QHBoxLayout(d)
        lg = QLabel()
        lg.setPixmap(marca.logo().scaledToHeight(130, Qt.TransformationMode.SmoothTransformation))
        lay.addWidget(lg)
        conv = 'LibreDWG (incluído)' if dwgconv.available() else 'não encontrado'
        t = QLabel(f'<h2 style="color:{marca.AZUL}">ElectraCad {marca.VERSAO}</h2>{marca.SUBTITULO}<br><br>'
                   f'Conversor de DWG: {conv}<br><small>LibreDWG é software livre (GPLv3): www.gnu.org/software/libredwg</small>')
        t.setWordWrap(True)
        lay.addWidget(t)
        d.exec()

    # ---------- projeto (JSON), folha, lista de materiais, recentes, tela limpa
    def recents(self):
        return [x for x in str(self.cfg.value('recent', '') or '').split('|') if x]

    def add_recent(self, p):
        try:
            lst = [p] + [x for x in self.recents() if x != p]
            self.cfg.setValue('recent', '|'.join(lst[:8]))
        except Exception:
            pass

    def fill_recent(self):
        self.m_recent.clear()
        lst = [x for x in self.recents() if os.path.isfile(x)]
        if not lst:
            self.m_recent.addAction('(nenhum)').setEnabled(False)
        for p in lst:
            a = self.m_recent.addAction(os.path.basename(p))
            a.triggered.connect(lambda _=False, p=p: self.open_path(p))

    def toggle_focus(self):
        self.focus = not self.focus
        for w in (self.dock_layers, self.dock_symbols, self.tool_bar):
            w.setVisible(not self.focus)
        self.say('Tela limpa ligada. Use Exibir > Tela limpa (ou Ctrl+Shift+F) para voltar.' if self.focus else 'Tela limpa desligada.')

    def toggle_grid(self):
        self.grid = not self.grid
        self.cv.update()

    def import_project(self):
        p, _ = QFileDialog.getOpenFileName(self, 'Importar projeto', '', 'Projeto ElectraCad (*.json)')
        if not p:
            return
        try:
            with open(p, encoding='utf-8-sig') as fh:
                data = projeto_io.parse(fh.read())
        except Exception as ex:
            return alert(self, 'Importar projeto', f'Não foi possível ler o projeto.\n{ex}')
        if not self.items:   # desenho vazio: adota a unidade do projeto
            self.unit_mm = projeto_io.file_unit_mm(data)
            self.sym_scale = 120.0 / self.unit_mm
            try:
                self.doc.header['$INSUNITS'] = {1000.0: 6, 10.0: 5, 1.0: 4}.get(self.unit_mm, 0)
            except Exception:
                pass
        res = {}

        def reg(e):
            self.create(e)
            return e
        try:
            self.do(lambda: res.update(projeto_io.apply(data, self.doc, self.msp, self.unit_mm, self.sym_scale, reg)))
        except Exception as ex:
            txt = log_exc('(importar projeto)')
            return alert(self, 'Importar projeto', f'Erro ao desenhar o projeto.\n{ex}', detail=txt)
        if res.get('circuitos'):
            self.circuits = res['circuitos']
        self.fill_layers()
        self.cv.fit()
        c = res['contagem']
        msg = (f'Projeto importado: {c["paredes"]} paredes, {c["ambientes"]} ambientes, {c["simbolos"]} símbolos, '
               f'{c["eletrodutos"]} eletrodutos, {len(res["circuitos"])} circuitos (abra Elétrica > Quadro de cargas).')
        self.say(msg)
        if res['avisos']:
            alert(self, 'Importar projeto', msg + '\n\nAvisos:\n' + '\n'.join(res['avisos'][:12]))

    def export_project(self):
        base = self.suggest or 'projeto'
        p, _ = QFileDialog.getSaveFileName(self, 'Exportar projeto', f'{base}.json', 'Projeto ElectraCad (*.json)')
        if not p:
            return
        try:
            d = projeto_io.export(self.msp, self.unit_mm, self.circuits, base)
            with open(p, 'w', encoding='utf-8') as fh:
                fh.write(projeto_io.dumps(d))
            self.say(f'Projeto exportado: {len(d["simbolos"])} símbolos e {len(d["circuitos"])} circuitos em {p}')
        except Exception as ex:
            alert(self, 'Exportar projeto', f'Não foi possível salvar.\n{ex}')

    def export_bom(self):
        rows = E.legend_rows(E.count_symbols(self.msp))
        if not rows:
            return self.say('Nenhum símbolo (bloco) encontrado no desenho.')
        p, _ = QFileDialog.getSaveFileName(self, 'Lista de materiais', 'lista_de_materiais.csv', 'CSV (*.csv)')
        if not p:
            return
        data = [[str(i), nome, str(n)] for i, (_, nome, n) in enumerate(rows, 1)]
        with open(p, 'w', encoding='utf-8-sig', newline='') as fh:
            fh.write(E.to_csv(['Item', 'Descrição', 'Quantidade'], data))
        self.say(f'Lista de materiais salva em {p}')

    def calc_quadro(self):
        if not self.circuits:
            self.say('Cadastre os circuitos primeiro: Elétrica > Quadro de cargas (ou importe um projeto).')
            return None
        return E.quadro(self.circuits, self.fd)

    def start_unifilar(self):
        if self.calc_quadro() is None:
            return
        self.begin('UNIPOS')

    def place_unifilar(self, p):
        q = self.calc_quadro()
        if q is None:
            return self.finish_cmd()
        k = self.text_height() / 2.5          # texto do diagrama com a altura de texto atual
        E.ensure_layers(self.doc)
        self.do(lambda: [self.create(e) for e in unifilar.draw_unifilar(self.msp, p, self.circuits, q, k)])
        self.fill_layers()
        self.finish_cmd('Diagrama unifilar inserido. Confira disjuntor geral, DR e DPS: são do projetista.')

    def export_cables(self):
        q = self.calc_quadro()
        if q is None:
            return
        p, _ = QFileDialog.getSaveFileName(self, 'Lista de cabos', 'lista_de_cabos.csv', 'CSV (*.csv)')
        if not p:
            return
        with open(p, 'w', encoding='utf-8-sig', newline='') as fh:
            fh.write(E.to_csv(E.CABLE_HEADER, E.cable_rows(self.circuits, q)))
        self.say(f'Lista de cabos salva em {p}')

    def sheet_dialog(self):
        d = QDialog(self)
        d.setWindowTitle('Folha com carimbo')
        lay = QVBoxLayout(d)
        form = QFormLayout()
        cfg = self.sheet_cfg
        cb_fmt, cb_or = QComboBox(), QComboBox()
        cb_fmt.addItems(list(folha.SHEETS))
        cb_fmt.setCurrentText(cfg.get('fmt', 'A3'))
        cb_or.addItems(['Paisagem', 'Retrato'])
        cb_or.setCurrentText(cfg.get('ori', 'Paisagem'))
        ed_scale = QLineEdit(cfg.get('scale', '1:50'))
        form.addRow('Formato:', cb_fmt)
        form.addRow('Orientação:', cb_or)
        form.addRow('Escala (1:N):', ed_scale)
        eds = {}
        for k in ('Projeto', 'Cliente', 'Conteúdo', 'Responsável técnico', 'Registro (CREA/CFT)', 'Data', 'Revisão', 'Folha'):
            eds[k] = QLineEdit(cfg.get('f', {}).get(k, ''))
            form.addRow(k + ':', eds[k])
        lay.addLayout(form)
        note = QLabel(f'Unidade do desenho: 1 unidade = {self.unit_mm:g} mm. Confira se está certo (Configurar > Tamanho dos símbolos).')
        note.setWordWrap(True)
        lay.addWidget(note)
        row = QHBoxLayout()
        row.addStretch(1)
        res = [False]
        b_ok, b_no = QPushButton('Posicionar folha'), QPushButton('Cancelar')
        b_ok.setDefault(True)
        b_ok.clicked.connect(lambda: (res.__setitem__(0, True), d.accept()))
        b_no.clicked.connect(d.reject)
        row.addWidget(b_no)
        row.addWidget(b_ok)
        lay.addLayout(row)
        d.exec()
        if not res[0]:
            return
        m = re.search(r'(\d+(?:[.,]\d+)?)\s*$', ed_scale.text().strip())
        den = float(m.group(1).replace(',', '.')) if m else 0
        if den <= 0:
            return alert(self, 'Folha', 'Escala inválida. Use o formato 1:50.')
        den = int(den) if den == int(den) else den
        self.sheet_cfg = {'fmt': cb_fmt.currentText(), 'ori': cb_or.currentText(), 'scale': f'1:{den}',
                          'f': {k: e.text() for k, e in eds.items()}}
        self.begin('SHEETPOS')
        self.st['sheet'] = {'fmt': cb_fmt.currentText(), 'portrait': cb_or.currentText() == 'Retrato', 'den': den,
                            'fields': {k: e.text() for k, e in eds.items()}}

    def place_sheet(self, p):
        sh = self.st.get('sheet')
        if not sh:
            return self.finish_cmd()
        E.ensure_layers(self.doc)
        ents = []
        self.do(lambda: ents.extend(self.create(e) and e for e in folha.draw_sheet(
            self.msp, p, sh['fmt'], sh['den'], self.unit_mm, sh['fields'], sh['portrait'])))
        W, H = folha.sheet_size(sh['fmt'], sh['portrait'])
        k = sh['den'] / self.unit_mm
        self.fill_layers()
        self.cv.zoom_to(p[0], p[1], p[0] + W * k, p[1] + H * k)
        self.finish_cmd('Folha inserida. Desenhe dentro da moldura.')

    def toggle_lw(self):
        self.show_lw = not self.show_lw
        self.cv.update()
        self.say('Espessuras de linha: ' + ('ligadas.' if self.show_lw else 'desligadas.'))

    def ask_sym_scale(self):
        v, ok = QInputDialog.getDouble(self, 'Tamanho dos símbolos',
                                       'Fator de escala (um símbolo mede ~2 unidades de largura com fator 1;\n'
                                       'use 12 para desenho em cm, 0,12 em metros, 120 em mm):',
                                       self.sym_scale, 1e-6, 1e9, 4)
        if ok and v > 0:
            self.sym_scale = v
            self.unit_mm = 120.0 / v

    def export_pdf(self):
        vis = [i.bbox for i in self.items if i.bbox]
        if not vis:
            return self.say('Nada para imprimir.')
        base = os.path.splitext(os.path.basename(self.path))[0] if self.path else 'desenho'
        path, _ = QFileDialog.getSaveFileName(self, 'Exportar PDF', f'{base}.pdf', 'PDF (*.pdf)')
        if not path:
            return
        x0, y0 = min(b[0] for b in vis), min(b[1] for b in vis)
        x1, y1 = max(b[2] for b in vis), max(b[3] for b in vis)
        wr = QPdfWriter(path)
        wr.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        wr.setPageOrientation(QPageLayout.Orientation.Landscape if x1 - x0 >= y1 - y0 else QPageLayout.Orientation.Portrait)
        wr.setResolution(150)
        wr.setPageMargins(QMarginsF(10, 10, 10, 10), QPageLayout.Unit.Millimeter)
        p = QPainter(wr)
        W, H = p.device().width(), p.device().height()
        z = min(W / max(x1 - x0, 1e-9), H / max(y1 - y0, 1e-9))
        ox, oy = (x0 + x1) / 2, (y0 + y1) / 2
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setTransform(QTransform(z, 0, 0, -z, W / 2 - z * ox, H / 2 + z * oy))
        self.cv.draw_scene(p, x0, y0, x1, y1, z, ox, oy, 150 / 25.4, True)
        p.end()
        self.say(f'PDF salvo em {path} (desenho ajustado à folha A4, sem escala fixa).')

    # ---------- comandos: edição
    def erase_sel(self):
        n = len(self.sel)
        for it in list(self.sel):
            self.remove(it)
        self.finish_cmd(f'{n} objeto(s) apagado(s).')

    def explode_sel(self):
        n = 0
        for it in list(self.sel):
            e = it.e
            if e.dxftype() not in ('LWPOLYLINE', 'POLYLINE', 'INSERT'):
                continue
            self._op.append(('del', e, e.copy()))
            new = list(e.explode())
            self.items.remove(it)
            for ne in new:
                self._op.append(('add', ne))
                self.new_item(ne)
            n += 1
        self.finish_cmd(f'{n} objeto(s) explodido(s).' if n else 'Nada a explodir (só polilinhas e blocos).')

    def transform_sel(self, mats, copy=False):
        for it in list(self.sel):
            e = None
            try:
                if copy:
                    e = it.e.copy()
                    self.msp.add_entity(e)
                    for m in mats:
                        e.transform(m)
                    self.create(e)
                else:
                    def f(ent):
                        for m in mats:
                            ent.transform(m)
                    self.modify(it, f)
            except Exception as ex:
                if copy and e is not None and e.is_alive and self.item_of(e) is None:
                    self.msp.delete_entity(e)
                self.say(f'Não foi possível transformar um objeto: {ex}')

    def rotate_sel(self, deg):
        b = self.pts[0]
        mats = [Matrix44.translate(-b[0], -b[1], 0), Matrix44.z_rotate(math.radians(deg)), Matrix44.translate(b[0], b[1], 0)]
        self.do(lambda: self.transform_sel(mats))
        self.finish_cmd('Girado.')

    def scale_sel(self, f):
        if f <= 0:
            return self.say('O fator deve ser maior que zero.')
        b = self.pts[0]
        mats = [Matrix44.translate(-b[0], -b[1], 0), Matrix44.scale(f, f, f), Matrix44.translate(b[0], b[1], 0)]
        self.do(lambda: self.transform_sel(mats))
        self.finish_cmd('Escalado.')

    def mirror_sel(self, a, b):
        if geom.dist(a, b) < 1e-12:
            return self.say('MIRROR: os dois pontos são iguais.')
        ang = math.atan2(b[1] - a[1], b[0] - a[0])
        mats = [Matrix44.translate(-a[0], -a[1], 0), Matrix44.z_rotate(-ang), Matrix44.scale(1, -1, 1),
                Matrix44.z_rotate(ang), Matrix44.translate(a[0], a[1], 0)]
        self.do(lambda: self.transform_sel(mats, copy=True))
        self.finish_cmd('Espelhado (o original foi mantido; apague-o com E se quiser).')

    # ---------- comandos: clicar em objetos (deslocar, aparar, estender, canto)
    def other_segments(self, skip, box=None):
        lc = self.layer_info()
        out = []
        for o in self.items:
            if o is skip or o.bbox is None or not lc.get(o.e.dxf.layer, DEFAULT_LC)[0]:
                continue
            b = o.bbox
            if box and (b[2] < box[0] or b[0] > box[2] or b[3] < box[1] or b[1] > box[3]):
                continue
            out += o.segments()
        return out

    def pick_cmd(self, p):
        c, st = self.cmd, self.st
        if c == 'OFFSET' and st.get('d') is None:
            return self.say('OFFSET: digite primeiro a distância e tecle Enter.')
        it = self.item_at(p, 10 / self.cv.z)
        if c == 'OFFSET':
            if st.get('obj') is None:
                if it is None:
                    return self.say('Nenhum objeto ali. Clique sobre a linha, círculo, arco ou polilinha.')
                if it.e.dxftype() not in ('LINE', 'CIRCLE', 'ARC', 'LWPOLYLINE'):
                    return self.say(f'Deslocar não funciona em {it.e.dxftype()}.')
                st['obj'] = it
                self.sel = {it}
                self.say('OFFSET: clique do lado para onde deslocar.')
            else:
                obj = st['obj']
                self.do(lambda: self.do_offset(obj, st['d'], p))
                st['obj'] = None
                self.sel.clear()
                self.say('OFFSET: clique o próximo objeto (Esc encerra).')
        elif c == 'TRIM':
            if it is None:
                return self.say('Nenhum objeto ali.')
            if it.e.dxftype() != 'LINE':
                return self.say('Aparar funciona só em linhas por enquanto.')
            a, b = self.line_pts(it)
            box = (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
            res = geom.trim_line(a, b, self.other_segments(it, box), p)
            if res is None:
                return self.say('Esse trecho não cruza nenhum outro objeto.')
            self.do(lambda: self.apply_trim(it, res))
            self.say('Aparado. Clique outro trecho (Esc encerra).')
        elif c == 'EXTEND':
            if it is None or it.e.dxftype() != 'LINE':
                return self.say('Clique perto da ponta de uma linha.')
            a, b = self.line_pts(it)
            end = 0 if geom.dist(p, a) <= geom.dist(p, b) else 1
            np_ = geom.extend_line(a, b, end, self.other_segments(it))
            if np_ is None:
                return self.say('Nenhum objeto no caminho para estender até ele.')
            z = it.e.dxf.start.z if end == 0 else it.e.dxf.end.z
            attr = 'start' if end == 0 else 'end'
            self.do(lambda: self.modify(it, lambda e: setattr(e.dxf, attr, Vec3(np_[0], np_[1], z))))
            self.say('Estendido. Clique outra linha (Esc encerra).')
        elif c == 'FILLET':
            if it is None or it.e.dxftype() != 'LINE':
                return self.say('Clique sobre uma linha.')
            if 'first' not in st:
                st['first'], st['p1'] = it, p
                self.sel = {it}
                return self.say('FILLET: clique a segunda linha.')
            f1, p1 = st['first'], st['p1']
            if it is f1:
                return self.say('Escolha outra linha.')
            a1, b1 = self.line_pts(f1)
            a2, b2 = self.line_pts(it)
            res = geom.fillet_corner(a1, b1, a2, b2, p1, p)
            self.st = {}
            self.sel.clear()
            if res is None:
                return self.say('As linhas são paralelas: não há canto para fechar.')
            self.do(lambda: (self.set_line(f1, *res[0]), self.set_line(it, *res[1])))
            self.say('Canto fechado. Clique a primeira linha de outro canto (Esc encerra).')
        self.cv.update()

    @staticmethod
    def line_pts(it):
        s, e = it.e.dxf.start, it.e.dxf.end
        return (s.x, s.y), (e.x, e.y)

    def set_line(self, it, a, b):
        zs, ze = it.e.dxf.start.z, it.e.dxf.end.z
        self.modify(it, lambda e: (setattr(e.dxf, 'start', Vec3(a[0], a[1], zs)), setattr(e.dxf, 'end', Vec3(b[0], b[1], ze))))

    def apply_trim(self, it, pieces):
        if not pieces:
            return self.remove(it)
        orig = it.e
        zs, ze = orig.dxf.start.z, orig.dxf.end.z
        extra = pieces[1:]
        a, b = pieces[0]
        self.modify(it, lambda e: (setattr(e.dxf, 'start', Vec3(a[0], a[1], zs)), setattr(e.dxf, 'end', Vec3(b[0], b[1], ze))))
        for a, b in extra:
            c = orig.copy()
            self.msp.add_entity(c)
            c.dxf.start, c.dxf.end = Vec3(a[0], a[1], zs), Vec3(b[0], b[1], ze)
            self.create(c)

    def do_offset(self, it, d, side):
        e, t = it.e, it.e.dxftype()
        if t == 'LINE':
            a, b = self.line_pts(it)
            na, nb = geom.offset_line(a, b, d, side)
            c = e.copy()
            self.msp.add_entity(c)
            c.dxf.start, c.dxf.end = Vec3(na[0], na[1], e.dxf.start.z), Vec3(nb[0], nb[1], e.dxf.end.z)
            self.create(c)
        elif t in ('CIRCLE', 'ARC'):
            ctr = wcs(e, e.dxf.center.x, e.dxf.center.y)
            r = e.dxf.radius
            nr = r + d if geom.dist(side, ctr) > r else r - d
            if nr <= 0:
                return self.say('A distância é maior que o raio.')
            c = e.copy()
            self.msp.add_entity(c)
            c.dxf.radius = nr
            self.create(c)
        elif t == 'LWPOLYLINE':
            pts = list(e.get_points('xyb'))
            if any(b for _, _, b in pts):
                return self.say('Deslocar ainda não funciona em polilinhas com trechos curvos.')
            P = [(x, y) for x, y, _ in pts]
            new = geom.offset_polyline(P, d * geom.side_of_polyline(P, e.closed, side), e.closed)
            c = e.copy()
            self.msp.add_entity(c)
            c.set_points(new, format='xy')
            self.create(c)

    # ---------- entrada por clique, digitação e números
    def point(self, p):
        c = self.cmd
        if c is None or self.selphase:
            return
        if c in PICKCMDS:
            return self.pick_cmd(p)
        q = self.pts
        q.append(p)
        n = len(q)
        if c == 'LINE':
            if n >= 2:
                self.do(lambda: self.add_line(q[-2], q[-1]))
        elif c == 'RECT':
            if n == 2:
                self.do(lambda: self.add_rect(q[0], q[1]))
                self.finish_cmd()
        elif c == 'CIRCLE':
            if n == 2:
                self.make_circle(geom.dist(q[0], q[1]))
        elif c == 'ARC':
            if n == 3:
                self.make_arc(*q)
        elif c == 'TEXT':
            self.make_text(p)
        elif c in ('MOVE', 'COPY'):
            if n == 2:
                mats = [Matrix44.translate(q[1][0] - q[0][0], q[1][1] - q[0][1], 0)]
                self.do(lambda: self.transform_sel(mats, c == 'COPY'))
                if c == 'MOVE':
                    self.finish_cmd('Movido.')
                else:
                    self.pts = [q[0]]
                    self.say('COPY: clique o próximo destino (Enter encerra).')
        elif c == 'ROTATE':
            if n == 2:
                self.rotate_sel(math.degrees(math.atan2(q[1][1] - q[0][1], q[1][0] - q[0][0])))
        elif c == 'SCALE':
            if n == 2:
                self.pts.pop()
                self.say('SCALE: digite o fator (ex.: 2) e tecle Enter.')
        elif c == 'MIRROR':
            if n == 2:
                self.mirror_sel(q[0], q[1])
        elif c == 'DIST':
            if n == 2:
                dx, dy = q[1][0] - q[0][0], q[1][1] - q[0][1]
                self.finish_cmd(f'Distância {math.hypot(dx, dy):.4f}   ΔX {dx:.4f}   ΔY {dy:.4f}   '
                                f'ângulo {math.degrees(math.atan2(dy, dx)):.2f}°')
        elif c == 'ZOOMW':
            if n == 2:
                self.cv.zoom_to(q[0][0], q[0][1], q[1][0], q[1][1])
                self.finish_cmd()
        elif c in ('DIMLINEAR', 'DIMALIGNED'):
            if n == 3:
                self.make_dim(q[0], q[1], q[2], c == 'DIMALIGNED')
        elif c == 'SYMBOL':
            q.pop()
            self.insert_sym(p)
        elif c == 'TABLE':
            q.pop()
            self.place_table(p)
        elif c == 'SHEETPOS':
            q.pop()
            self.place_sheet(p)
        elif c == 'UNIPOS':
            q.pop()
            self.place_unifilar(p)
        self.cv.refresh_cursor()
        self.cv.update()

    def direction_point(self, v):
        """Ponto a v unidades do último ponto, na direção do mouse (já com orto/polar)."""
        o = self.pts[-1]
        m = self.cv.cur[0]
        dx, dy = m[0] - o[0], m[1] - o[1]
        L = math.hypot(dx, dy)
        ux, uy = (dx / L, dy / L) if L > 1e-12 else (1.0, 0.0)
        return (o[0] + ux * v, o[1] + uy * v)

    def wants_number(self):
        c, n = self.cmd, len(self.pts)
        return (c == 'CIRCLE' and n == 1) or (c in ('ROTATE', 'SCALE') and n == 1) or \
               (c == 'OFFSET' and self.st.get('d') is None)

    def number(self, v):
        c, n = self.cmd, len(self.pts)
        if c in DRAW_REL and n >= 1:
            return self.point(self.direction_point(v))
        if c == 'CIRCLE' and n == 1:
            return self.make_circle(v)
        if c == 'ROTATE' and n == 1:
            return self.rotate_sel(v)
        if c == 'SCALE' and n == 1:
            return self.scale_sel(v)
        if c == 'OFFSET' and self.st.get('d') is None:
            if v > 0:
                self.st['d'] = v
                return self.say(f'OFFSET: distância {v:g}. Clique o objeto.')
            return self.say('A distância deve ser maior que zero.')
        self.say('Número não esperado agora.')

    @staticmethod
    def num(t):
        try:
            return float(t.replace(',', '.'))
        except ValueError:
            return None

    def on_cmd(self):
        t = self.cmd_edit.text().strip()
        self.cmd_edit.clear()
        self.cv.setFocus()
        if not t:
            if self.cmd is None and self.last_cmd:
                return self.begin(self.last_cmd)
            return self.enter()
        u, c, n = t.upper(), self.cmd, len(self.pts)
        if c == 'LAYER' and u not in CMDS:
            self.make_layer(t)
            return self.finish_cmd(f'Camada atual: {t}')
        if u == 'C' and c in ('LINE', 'PLINE') and n > 2:
            if c == 'LINE':
                self.do(lambda: self.add_line(self.pts[-1], self.pts[0]))
            else:
                self.do(lambda: self.add_pline(self.pts, True))
            return self.finish_cmd()
        if c == 'SYMBOL' and u == 'R':
            self.st['rot'] = (self.st.get('rot', 0) + 90) % 360
            self.cv.update()
            return self.say(f'Símbolo girado: {self.st["rot"]}°. Clique para inserir.')
        if u in CMDS:
            return self.begin(CMDS[u])
        if c and not self.selphase:
            if self.wants_number():
                v = self.num(t)
                if v is not None:
                    return self.number(v)
            pt = geom.parse_point(t, self.pts[-1] if self.pts else (0.0, 0.0))
            if pt:
                return self.point(pt)
            v = self.num(t)
            if v is not None:
                return self.number(v)
        self.say(f'Não entendi: {t}')


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setApplicationName('ElectraCad')
    app.setStyle('Fusion')
    app.setStyleSheet(marca.STYLE)
    app.setWindowIcon(marca.app_icon())
    try:
        set_theme(str(QSettings('ElectraCad', 'app').value('light', 'true')).lower() != 'false')
    except Exception:
        pass
    splash = QSplashScreen(marca.splash_pixmap('Carregando…'))
    splash.show()
    app.processEvents()
    try:
        w = Main()
    except Exception:
        # erro na abertura: mostra numa janela (antes de iniciar o laço do Qt, o aviso comum não aparece)
        txt = log_exc('(erro ao iniciar)')
        alert(None, 'ElectraCad', f'Não foi possível iniciar o ElectraCad.\n\nO erro foi gravado em:\n{LOG}', detail=txt)
        sys.exit(1)
    w.showMaximized()
    splash.finish(w)
    sys.exit(app.exec())
