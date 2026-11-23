"""Diagrama unifilar automático a partir do quadro de cargas (lógica de desenho, sem Qt).

É um esquema de apoio: o disjuntor geral, o DR/DPS e a proteção de cada circuito devem ser definidos e conferidos
pelo projetista responsável. Medidas em milímetros de papel multiplicadas por `k` (unidades do desenho por mm).
"""
import eletrica as E

LAYER = 'ELE-UNIFILAR'
COL_W = 26.0


def draw_unifilar(layout, origin, ckts, q, k, title='QUADRO DE DISTRIBUIÇÃO'):
    ox, oy = origin
    ents = []
    attr = lambda: {'layer': LAYER}

    def X(v): return ox + v * k
    def Y(v): return oy + v * k

    def line(x0, y0, x1, y1):
        ents.append(layout.add_line((X(x0), Y(y0)), (X(x1), Y(y1)), dxfattribs=attr()))

    def rect(x0, y0, x1, y1):
        ents.append(layout.add_lwpolyline([(X(x0), Y(y0)), (X(x1), Y(y0)), (X(x1), Y(y1)), (X(x0), Y(y1))],
                                          close=True, dxfattribs=attr()))

    def text(s, x, y, h=2.5):
        if s:
            ents.append(layout.add_text(str(s), dxfattribs={'layer': LAYER, 'height': h * k, 'insert': (X(x), Y(y))}))

    n = len(ckts)
    width = 36 + n * COL_W
    text(title, 0, 56, 3.5)
    text(f'Total instalado: {E.fmt(q["total"], 0)} VA   Demanda: {E.fmt(q["demanda"], 0)} VA', 0, 50, 2.5)
    # alimentação e disjuntor geral (a dimensionar pelo projetista)
    line(12, 46, 12, 28)
    text('ALIMENTAÇÃO', 15, 44, 2.2)
    rect(8, 22, 16, 28)
    text('DG', 9.2, 24, 2.5)
    text('a dimensionar', 17, 24, 2.0)
    line(12, 22, 12, 0)
    # barramento
    line(4, 0, width, 0)
    text(f'Barramento: fases A {E.fmt(q["tot"]["A"], 0)} / B {E.fmt(q["tot"]["B"], 0)} / C {E.fmt(q["tot"]["C"], 0)} VA',
         4, 3, 2.0)
    for i, (c, d, f) in enumerate(zip(ckts, q['res'], q['fases'])):
        x = 36 + i * COL_W
        line(x, 0, x, -8)
        rect(x - 3, -8, x + 3, -16)                       # disjuntor do circuito
        text(E.fmt(d['disjuntor'], 0) + 'A' if d['disjuntor'] else '?', x + 4, -13, 2.2)
        line(x, -16, x, -40)
        pre = x - COL_W / 2 + 2
        text(f'C{c["num"]}', x - 2, -44, 3.0)
        text(str(c['nome'])[:15], pre, -49, 2.0)
        text(f'{E.fmt(d["secao"])} mm²' if d['secao'] else 'dimensionar', pre, -53, 2.0)
        text(f'{c["fases"]} {E.fmt(c["v"], 0)}V', pre, -57, 2.0)
        text(f'{E.fmt(c["va"], 0)} VA', pre, -61, 2.0)
        text(f'Fase {f}', pre, -65, 2.0)
    return ents
