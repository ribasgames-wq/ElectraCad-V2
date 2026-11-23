"""Folha de desenho com moldura e carimbo (lógica de desenho, sem Qt).

Medidas em milímetros de PAPEL; `den` é o denominador da escala (1:50 -> 50) e `unit_mm` quanto vale uma unidade do
desenho em mm (cm = 10, m = 1000). A moldura segue um layout usual (margem esquerda maior, para furar/encadernar);
confira com o padrão da sua empresa ou do seu cliente.
"""
SHEETS = {'A4': (297, 210), 'A3': (420, 297), 'A2': (594, 420), 'A1': (841, 594), 'A0': (1189, 841)}
FIELDS = ['Projeto', 'Cliente', 'Conteúdo', 'Responsável técnico', 'Registro (CREA/CFT)', 'Data', 'Revisão', 'Folha']


def sheet_size(fmt, portrait=False):
    w, h = SHEETS[fmt]
    return (h, w) if portrait else (w, h)


def draw_sheet(layout, origin, fmt, den, unit_mm, fields, portrait=False, layer='ELE-TABELAS'):
    """Desenha moldura e carimbo com o canto inferior esquerdo da folha em `origin`. Devolve as entidades criadas."""
    k = den / unit_mm                       # unidades do desenho por mm de papel
    W, H = sheet_size(fmt, portrait)
    ox, oy = origin
    ents = []
    attr = lambda: {'layer': layer}

    def X(v): return ox + v * k
    def Y(v): return oy + v * k

    def rect(x0, y0, x1, y1):
        ents.append(layout.add_lwpolyline([(X(x0), Y(y0)), (X(x1), Y(y0)), (X(x1), Y(y1)), (X(x0), Y(y1))],
                                          close=True, dxfattribs=attr()))

    def line(x0, y0, x1, y1):
        ents.append(layout.add_line((X(x0), Y(y0)), (X(x1), Y(y1)), dxfattribs=attr()))

    def text(s, x, y, h):
        if s:
            ents.append(layout.add_text(str(s), dxfattribs={'layer': layer, 'height': h * k, 'insert': (X(x), Y(y))}))

    rect(0, 0, W, H)                                    # borda da folha
    ml, mo = 25, 10                                     # margens: esquerda e demais
    ix0, iy0, ix1, iy1 = ml, mo, W - mo, H - mo
    rect(ix0, iy0, ix1, iy1)                            # moldura
    bw = min(175.0, ix1 - ix0)
    bx0, bx1 = ix1 - bw, ix1
    rh = 9.0
    rows = [[('Projeto', 1.0)], [('Cliente', 1.0)], [('Conteúdo', 1.0)],
            [('Responsável técnico', 0.6), ('Registro (CREA/CFT)', 0.4)],
            [('Data', 0.3), ('Escala', 0.25), ('Folha', 0.25), ('Revisão', 0.2)]]
    n = len(rows)
    top = iy0 + n * rh
    fields = dict(fields or {})
    fields.setdefault('Escala', f'1:{den}')
    for i, row in enumerate(rows):
        y1 = top - i * rh
        y0 = y1 - rh
        x = bx0
        for label, frac in row:
            x1c = bx1 if (label, frac) == row[-1] else x + bw * frac
            rect(x, y0, x1c, y1)
            text(label, x + 1, y1 - 3.2, 1.8)
            text(fields.get(label, ''), x + 1, y0 + 1.6, 3.2)
            x = x1c
    return ents
