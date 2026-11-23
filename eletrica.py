"""Recursos de projeto elétrico do ElectraCad.

A parte de dados e cálculos é pura (sem Qt). As funções que recebem `doc`/`layout` usam a API do ezdxf.

AVISO: os símbolos são de uso comum no Brasil, mas NÃO foram conferidos contra o texto da NBR 5444 (norma paga).
Os valores de condução de corrente vêm da NBR 5410, tabela 36 (cobre, PVC, método B1). Tudo aqui é apoio ao
projetista: a conferência e a responsabilidade técnica são do profissional habilitado.
"""
import csv
import io
import math
from collections import Counter

PREFIX = 'ELEC_'
S2 = math.sqrt(0.5)


# ------------------------------------------------------------------ primitivas dos símbolos
def C(cx, cy, r):
    return ('circle', (cx, cy), r)


def L(x1, y1, x2, y2):
    return ('line', (x1, y1), (x2, y2))


def P(pts, closed=True):
    return ('poly', list(pts), closed)


def T(txt, x, y, h=0.8):
    """Texto centralizado em (x, y)."""
    return ('text', txt, (x, y), h)


def text_origin(txt, x, y, h):
    """Ponto de inserção (canto inferior esquerdo) para centralizar o texto em (x, y)."""
    return (x - len(txt) * h * 0.3, y - h * 0.5)


def _tick(t, half=0.3):
    """Traço curto atravessando a haste do interruptor (que vai de (.35,.35) a (1.5,1.5)), no ponto t de 0 a 1."""
    x = 0.35 + 1.15 * t
    d = half * S2
    return L(x - d, x + d, x + d, x - d)


_TRI = [(-1, -0.6), (1, -0.6), (0, 1.1)]
_RECT = lambda a, b: [(-a, -b), (a, -b), (a, b), (-a, b)]

# (id, nome, categoria, camada, primitivas)
_DEFS = [
    ('luz_teto', 'Ponto de luz no teto', 'Iluminação', 'ELE-ILUMINACAO',
     [C(0, 0, 1), L(-S2, -S2, S2, S2), L(-S2, S2, S2, -S2)]),
    ('arandela', 'Arandela (luz na parede)', 'Iluminação', 'ELE-ILUMINACAO',
     [C(0, 0, 0.8), L(-1.4, -0.8, 1.4, -0.8)]),
    ('fluorescente', 'Luminária fluorescente', 'Iluminação', 'ELE-ILUMINACAO',
     [P(_RECT(2, 0.5)), L(-2, 0, 2, 0)]),
    ('embutido', 'Luminária embutida (spot)', 'Iluminação', 'ELE-ILUMINACAO',
     [C(0, 0, 1), C(0, 0, 0.35)]),
    ('emergencia', 'Luminária de emergência', 'Iluminação', 'ELE-ILUMINACAO',
     [C(0, 0, 1), T('E', 0, 0, 1.0)]),
    ('int_1s', 'Interruptor simples (1 seção)', 'Interruptores', 'ELE-INTERRUPTORES',
     [C(0, 0, 0.5), L(0.35, 0.35, 1.5, 1.5), T('S', 1.9, 1.9, 0.8)]),
    ('int_2s', 'Interruptor de 2 seções', 'Interruptores', 'ELE-INTERRUPTORES',
     [C(0, 0, 0.5), L(0.35, 0.35, 1.5, 1.5), _tick(0.45), _tick(0.8), T('S', 1.9, 1.9, 0.8)]),
    ('int_paralelo', 'Interruptor paralelo (three-way)', 'Interruptores', 'ELE-INTERRUPTORES',
     [C(0, 0, 0.5), L(0.35, 0.35, 1.5, 1.5), T('S3', 2.1, 1.9, 0.8)]),
    ('dimmer', 'Dimmer', 'Interruptores', 'ELE-INTERRUPTORES',
     [C(0, 0, 0.5), L(0.35, 0.35, 1.5, 1.5), T('D', 1.9, 1.9, 0.8)]),
    ('sensor_presenca', 'Sensor de presença', 'Interruptores', 'ELE-INTERRUPTORES',
     [C(0, 0, 1), T('SP', 0, 0, 0.7)]),
    ('tomada_baixa', 'Tomada baixa (0,30 m)', 'Tomadas', 'ELE-TOMADAS',
     [P(_TRI), L(0, -0.6, 0, -1.3)]),
    ('tomada_media', 'Tomada média (1,30 m)', 'Tomadas', 'ELE-TOMADAS',
     [P(_TRI), L(0.5, 0.25, 1.4, 0.25)]),
    ('tomada_alta', 'Tomada alta (2,00 m)', 'Tomadas', 'ELE-TOMADAS',
     [P(_TRI), L(0, 1.1, 0, 1.8)]),
    ('tue', 'Tomada de uso específico (TUE)', 'Tomadas', 'ELE-TOMADAS',
     [P(_TRI), C(0, -0.05, 0.25)]),
    ('quadro_dist', 'Quadro de distribuição', 'Quadros e caixas', 'ELE-QUADROS',
     [P(_RECT(1.5, 1)), T('QD', 0, 0, 0.9)]),
    ('medidor', 'Medidor (kWh)', 'Quadros e caixas', 'ELE-QUADROS',
     [P(_RECT(1.5, 1)), T('kWh', 0, 0, 0.7)]),
    ('caixa_passagem', 'Caixa de passagem', 'Quadros e caixas', 'ELE-QUADROS',
     [P(_RECT(0.7, 0.7))]),
    ('ventilador', 'Ventilador de teto', 'Equipamentos', 'ELE-EQUIPAMENTOS',
     [C(0, 0, 1), C(0, 0, 0.2), L(0.2, 0, 1, 0), L(-0.2, 0, -1, 0), L(0, 0.2, 0, 1), L(0, -0.2, 0, -1)]),
    ('ar_cond', 'Ar-condicionado', 'Equipamentos', 'ELE-EQUIPAMENTOS',
     [P(_RECT(1.5, 0.8)), T('AC', 0, 0, 0.8)]),
    ('motor', 'Motor', 'Equipamentos', 'ELE-EQUIPAMENTOS',
     [C(0, 0, 1), T('M', 0, 0, 1.0)]),
    ('campainha', 'Campainha / cigarra', 'Equipamentos', 'ELE-EQUIPAMENTOS',
     [C(0, 0, 1), T('CP', 0, 0, 0.7)]),
    ('terra', 'Aterramento', 'Aterramento', 'ELE-ATERRAMENTO',
     [L(0, 1.2, 0, 0), L(-1, 0, 1, 0), L(-0.65, -0.35, 0.65, -0.35), L(-0.3, -0.7, 0.3, -0.7)]),
]

SYMBOLS = {d[0]: {'id': d[0], 'nome': d[1], 'cat': d[2], 'layer': d[3], 'prims': d[4]} for d in _DEFS}
ORDER = [d[0] for d in _DEFS]
CATEGORIAS = []
for _d in _DEFS:
    if _d[2] not in CATEGORIAS:
        CATEGORIAS.append(_d[2])


def block_name(sid):
    return PREFIX + sid.upper()


def symbol_id(name):
    """Id do símbolo a partir do nome do bloco, ou None se não for um símbolo do ElectraCad."""
    if name and name.upper().startswith(PREFIX):
        sid = name[len(PREFIX):].lower()
        if sid in SYMBOLS:
            return sid
    return None


def extents(prims):
    """Caixa (x0, y0, x1, y1) que contém as primitivas (para centralizar os ícones)."""
    xs, ys = [], []
    for pr in prims:
        k = pr[0]
        if k == 'line':
            xs += [pr[1][0], pr[2][0]]
            ys += [pr[1][1], pr[2][1]]
        elif k == 'circle':
            (cx, cy), r = pr[1], pr[2]
            xs += [cx - r, cx + r]
            ys += [cy - r, cy + r]
        elif k == 'poly':
            xs += [p[0] for p in pr[1]]
            ys += [p[1] for p in pr[1]]
        elif k == 'text':
            txt, (x, y), h = pr[1], pr[2], pr[3]
            w = len(txt) * h * 0.6
            xs += [x - w / 2, x + w / 2]
            ys += [y - h / 2, y + h / 2]
    return (min(xs), min(ys), max(xs), max(ys))


# ------------------------------------------------------------------ camadas elétricas padrão
# (nome, cor ACI, tipo de linha, espessura em centésimos de mm)
LAYERS = [
    ('ELE-ILUMINACAO', 2, 'CONTINUOUS', 25),
    ('ELE-INTERRUPTORES', 3, 'CONTINUOUS', 25),
    ('ELE-TOMADAS', 4, 'CONTINUOUS', 25),
    ('ELE-QUADROS', 1, 'CONTINUOUS', 50),
    ('ELE-EQUIPAMENTOS', 6, 'CONTINUOUS', 25),
    ('ELE-ATERRAMENTO', 3, 'CONTINUOUS', 25),
    ('ELE-ELETRODUTO-TETO', 5, 'CONTINUOUS', 25),
    ('ELE-ELETRODUTO-PISO', 5, 'DASHED', 25),
    ('ELE-TEXTO', 7, 'CONTINUOUS', 18),
    ('ELE-TABELAS', 7, 'CONTINUOUS', 18),
    ('ELE-UNIFILAR', 5, 'CONTINUOUS', 25),
]
LAYER_ELETRODUTO_TETO = 'ELE-ELETRODUTO-TETO'
LAYER_ELETRODUTO_PISO = 'ELE-ELETRODUTO-PISO'
_LT_PATTERNS = {'DASHED': [0.75, 0.5, -0.25]}


def _ensure_linetype(doc, name):
    """Garante que o tipo de linha exista no desenho; devolve o nome a usar (CONTINUOUS se não der)."""
    if name.upper() == 'CONTINUOUS':
        return 'CONTINUOUS'
    try:
        if name in doc.linetypes:
            return name
        pat = _LT_PATTERNS.get(name.upper())
        if pat:
            doc.linetypes.add(name, pattern=pat, description=name)
            return name
    except Exception:
        pass
    return 'CONTINUOUS'


def ensure_layers(doc):
    """Cria as camadas elétricas que ainda não existem. Devolve a lista dos nomes criados."""
    created = []
    for name, color, lt, lw in LAYERS:
        if name in doc.layers:
            continue
        lay = doc.layers.add(name)
        lay.color = color
        lay.dxf.linetype = _ensure_linetype(doc, lt)
        lay.dxf.lineweight = lw
        created.append(name)
    return created


# ------------------------------------------------------------------ blocos e inserção
def ensure_block(doc, sid):
    """Cria (se preciso) a definição do bloco do símbolo e devolve o nome do bloco."""
    name = block_name(sid)
    if name in doc.blocks:
        return name
    blk = doc.blocks.new(name=name)
    for pr in SYMBOLS[sid]['prims']:
        k = pr[0]
        if k == 'line':
            blk.add_line(pr[1], pr[2])
        elif k == 'circle':
            blk.add_circle(pr[1], pr[2])
        elif k == 'poly':
            blk.add_lwpolyline(pr[1], close=pr[2])
        elif k == 'text':
            txt, (x, y), h = pr[1], pr[2], pr[3]
            blk.add_text(txt, dxfattribs={'height': h, 'insert': text_origin(txt, x, y, h)})
    return name


def insert_symbol(doc, layout, sid, pos, scale, rotation=0.0, layer=None):
    ensure_layers(doc)
    name = ensure_block(doc, sid)
    return layout.add_blockref(name, (pos[0], pos[1]), dxfattribs={
        'layer': layer or SYMBOLS[sid]['layer'], 'xscale': scale, 'yscale': scale, 'zscale': scale,
        'rotation': rotation})


# ------------------------------------------------------------------ contagem e legenda
def count_symbols(layout):
    """Conta as inserções de blocos no desenho: Counter {nome do bloco: quantidade}."""
    cnt = Counter()
    for e in layout:
        if e.dxftype() == 'INSERT':
            name = e.dxf.name
            if name and not name.startswith('*'):
                cnt[name] += 1
    return cnt


def legend_rows(counter):
    """[(id do símbolo ou None, descrição, quantidade)], símbolos conhecidos primeiro, na ordem da biblioteca."""
    known, other = [], []
    for name, n in counter.items():
        sid = symbol_id(name)
        if sid:
            known.append((ORDER.index(sid), sid, SYMBOLS[sid]['nome'], n))
        else:
            other.append((name.lower(), None, name, n))
    known.sort()
    other.sort()
    return [(sid, nome, n) for _, sid, nome, n in known] + [(sid, nome, n) for _, sid, nome, n in other]


def auto_col_widths(rows, text_h, sym_w=None):
    pad = text_h * 0.4
    sym_w = sym_w or text_h * 3
    ncol = max(len(r) for r in rows)
    out = []
    for j in range(ncol):
        w = 0.0
        for r in rows:
            if j >= len(r) or r[j] in (None, ''):
                continue
            cell = r[j]
            w = max(w, sym_w if isinstance(cell, tuple) else len(str(cell)) * text_h * 0.62 + 2 * pad)
        out.append(max(w, text_h * 2))
    return out


def draw_table(doc, layout, origin, rows, col_w, row_h, text_h, layer='ELE-TABELAS', sym_scale=None):
    """Desenha uma tabela com o canto superior esquerdo em `origin`. Uma célula ('sym', id) vira um símbolo.
    Devolve a lista de entidades criadas."""
    ents = []
    x0, y0 = origin
    nrow = len(rows)
    width, height = sum(col_w), row_h * nrow
    attr = {'layer': layer}
    for i in range(nrow + 1):
        y = y0 - i * row_h
        ents.append(layout.add_line((x0, y), (x0 + width, y), dxfattribs=dict(attr)))
    xs = [x0]
    for w in col_w:
        xs.append(xs[-1] + w)
    for x in xs:
        ents.append(layout.add_line((x, y0), (x, y0 - height), dxfattribs=dict(attr)))
    pad = text_h * 0.4
    for i, row in enumerate(rows):
        top = y0 - i * row_h
        for j, cell in enumerate(row):
            if cell in (None, ''):
                continue
            if isinstance(cell, tuple) and cell[0] == 'sym':
                name = ensure_block(doc, cell[1])
                s = sym_scale or min(row_h, col_w[j]) * 0.28
                ents.append(layout.add_blockref(name, (xs[j] + col_w[j] / 2, top - row_h / 2), dxfattribs={
                    'layer': SYMBOLS[cell[1]]['layer'], 'xscale': s, 'yscale': s, 'zscale': s}))
            else:
                ents.append(layout.add_text(str(cell), dxfattribs={
                    'layer': layer, 'height': text_h, 'insert': (xs[j] + pad, top - row_h / 2 - text_h / 2)}))
    return ents


# ------------------------------------------------------------------ quadro de cargas
# NBR 5410, tabela 36: cobre, PVC, método B1 (eletroduto embutido em alvenaria), 30 °C.
# seção mm² : (2 condutores carregados, 3 condutores carregados) em ampères
AMPACITY_B1 = {1.5: (17.5, 15.5), 2.5: (24, 21), 4: (32, 28), 6: (41, 36), 10: (57, 50),
               16: (76, 68), 25: (101, 89), 35: (125, 110), 50: (151, 134)}
SECOES = sorted(AMPACITY_B1)
DISJUNTORES = [10, 16, 20, 25, 32, 40, 50, 63, 70, 80, 90, 100, 125]   # correntes nominais comerciais comuns
TIPOS = ('Iluminação', 'TUG', 'TUE')
MIN_SECAO = {'Iluminação': 1.5, 'TUG': 2.5, 'TUE': 2.5}                  # NBR 5410, tabela 47 (cobre)
FASES = ('F+N', 'F+F', '3F')


def corrente(va, v, fases):
    """Corrente de projeto em A a partir da potência aparente (VA) e da tensão (V)."""
    if v <= 0:
        return 0.0
    return va / (math.sqrt(3) * v) if fases == '3F' else va / v


def dimensionar(tipo, va, v, fases):
    """Escolhe a menor seção e o menor disjuntor com Ib <= In <= Iz, respeitando a seção mínima do tipo."""
    ib = corrente(va, v, fases)
    col = 1 if fases == '3F' else 0
    smin = MIN_SECAO.get(tipo, 2.5)
    for s in SECOES:
        if s < smin:
            continue
        iz = AMPACITY_B1[s][col]
        for d in DISJUNTORES:
            if d >= ib - 1e-9:
                if d <= iz:
                    return {'i': ib, 'secao': s, 'disjuntor': d, 'iz': iz, 'aviso': ''}
                break   # o menor disjuntor possível passa da capacidade desta seção: tenta a seção maior
    return {'i': ib, 'secao': None, 'disjuntor': None, 'iz': None,
            'aviso': 'Corrente acima do que a tabela cobre: dimensionar manualmente'}


def balancear(ckts):
    """Distribui os circuitos entre as fases A, B e C. Devolve ([fase de cada circuito], {fase: VA})."""
    tot = {'A': 0.0, 'B': 0.0, 'C': 0.0}
    out = [None] * len(ckts)
    for i in sorted(range(len(ckts)), key=lambda k: -ckts[k]['va']):
        c = ckts[i]
        if c['fases'] == '3F':
            out[i] = 'ABC'
            for k in tot:
                tot[k] += c['va'] / 3
        elif c['fases'] == 'F+F':
            a, b = min((('A', 'B'), ('B', 'C'), ('A', 'C')), key=lambda pr: tot[pr[0]] + tot[pr[1]])
            out[i] = a + b
            tot[a] += c['va'] / 2
            tot[b] += c['va'] / 2
        else:
            k = min(tot, key=lambda x: tot[x])
            out[i] = k
            tot[k] += c['va']
    return out, tot


def fmt(x, dec=1):
    """Número no formato brasileiro (vírgula decimal). Inteiros saem sem casas."""
    if x is None:
        return '—'
    if dec == 0 or abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f'{x:.{dec}f}'.replace('.', ',')


HEADER = ['Nº', 'Descrição', 'Tipo', 'V', 'Fases', 'Pot. (VA)', 'I (A)', 'Seção (mm²)', 'Disj. (A)', 'Fase']


def quadro(ckts, fd=1.0):
    """Calcula o quadro. Cada circuito: {'num','nome','tipo','v','fases','va'}."""
    res = [dimensionar(c['tipo'], c['va'], c['v'], c['fases']) for c in ckts]
    fases, tot = balancear(ckts)
    rows = []
    for c, d, f in zip(ckts, res, fases):
        rows.append([str(c['num']), c['nome'], c['tipo'], fmt(c['v'], 0), c['fases'], fmt(c['va'], 0),
                     fmt(d['i'], 1), fmt(d['secao']), fmt(d['disjuntor'], 0), f])
    total = sum(c['va'] for c in ckts)
    demanda = total * fd

    def foot(label, value):
        return ['', label, '', '', '', value, '', '', '', '']
    footer = [foot('Total instalado (VA)', fmt(total, 0)), foot('Fator de demanda', fmt(fd, 2)),
              foot('Demanda (VA)', fmt(demanda, 0)), foot('Carga na fase A (VA)', fmt(tot['A'], 0)),
              foot('Carga na fase B (VA)', fmt(tot['B'], 0)), foot('Carga na fase C (VA)', fmt(tot['C'], 0))]
    return {'header': HEADER, 'rows': rows, 'footer': footer, 'res': res, 'fases': fases, 'tot': tot,
            'total': total, 'demanda': demanda}


def to_csv(header, rows, footer=()):
    """Texto CSV com ponto e vírgula (abre direto no Excel em português)."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';', lineterminator='\n')
    w.writerow(header)
    w.writerows(rows)
    w.writerows(footer)
    return buf.getvalue()


COND_TXT = {'F+N': 'F, N, PE', 'F+F': 'F, F, PE', '3F': 'F, F, F, PE'}


def cable_rows(ckts, q):
    """Linhas da lista de cabos: um item por circuito (condutores, seção, disjuntor, corrente)."""
    out = []
    for c, d, f in zip(ckts, q['res'], q['fases']):
        out.append([str(c['num']), c['nome'], c['tipo'], fmt(c['v'], 0), c['fases'], COND_TXT.get(c['fases'], ''),
                    fmt(d['secao']), fmt(d['disjuntor'], 0), fmt(c['va'], 0), fmt(d['i'], 1), f])
    return out


CABLE_HEADER = ['Circuito', 'Descrição', 'Tipo', 'V', 'Fases', 'Condutores', 'Seção (mm²)', 'Disj. (A)', 'Pot. (VA)', 'I (A)', 'Fase']
