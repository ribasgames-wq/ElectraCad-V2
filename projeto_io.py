"""Troca de projetos em JSON (por exemplo, gerados por IA no aplicativo ElectraCad do Base44) com o ElectraCad desktop.

Formato "electracad-projeto" versão 1: veja FORMATO_PROJETO.md. Coordenadas na unidade indicada em "unidade" (mm, cm ou m),
com o eixo Y para cima.
"""
import json
import math

import eletrica as E

UNIT_MM = {'mm': 1.0, 'cm': 10.0, 'm': 1000.0}
L_PAREDE = 'ARQ-PAREDES'


def _num(v, what):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or abs(v) > 1e9:
        raise ValueError(f'valor inválido em {what}: {v!r}')
    return float(v)


def _pt(p, what):
    if not isinstance(p, (list, tuple)) or len(p) < 2:
        raise ValueError(f'ponto inválido em {what}: {p!r}')
    return _num(p[0], what), _num(p[1], what)


def parse(text):
    try:
        data = json.loads(text)
    except ValueError as ex:
        raise ValueError(f'o arquivo não é um JSON válido ({ex})')
    if not isinstance(data, dict) or data.get('formato') != 'electracad-projeto':
        raise ValueError('este arquivo não é um projeto ElectraCad (falta "formato": "electracad-projeto").')
    if data.get('unidade', 'm') not in UNIT_MM:
        raise ValueError('"unidade" deve ser "mm", "cm" ou "m".')
    return data


def file_unit_mm(data):
    return UNIT_MM[data.get('unidade', 'm')]


def read_circuits(data, warns):
    out = []
    for i, c in enumerate(data.get('circuitos') or [], 1):
        try:
            nome = str(c.get('nome') or f'Circuito {i}')
            tipo = c.get('tipo', 'TUG')
            tipo = tipo if tipo in E.TIPOS else 'TUG'
            fases = c.get('fases', 'F+N')
            fases = fases if fases in E.FASES else 'F+N'
            v, va = _num(c.get('tensao', 127), 'tensão'), _num(c.get('potencia_va'), 'potência')
            if v <= 0 or va <= 0:
                raise ValueError('tensão e potência devem ser positivas')
            out.append({'num': len(out) + 1, 'nome': nome, 'tipo': tipo, 'v': v, 'fases': fases, 'va': va})
        except Exception as ex:
            warns.append(f'Circuito {i} ignorado: {ex}')
    return out


def apply(data, doc, layout, unit_mm, sym_scale, reg=lambda e: e):
    """Desenha o projeto no layout. `reg(entidade)` é chamada para cada objeto criado (usada no desfazer).
    Devolve {'contagem': {...}, 'avisos': [...], 'circuitos': [...]}."""
    warns = []
    k = file_unit_mm(data) / unit_mm
    E.ensure_layers(doc)
    if L_PAREDE not in doc.layers:
        doc.layers.add(L_PAREDE).color = 7
    th = 150.0 / unit_mm            # texto de ~15 cm reais
    cnt = {'paredes': 0, 'ambientes': 0, 'simbolos': 0, 'eletrodutos': 0}

    for i, w in enumerate(data.get('paredes') or [], 1):
        try:
            pts = [_pt(p, f'parede {i}') for p in w.get('pontos', [])]
            if len(pts) < 2:
                raise ValueError('precisa de 2 pontos ou mais')
            reg(layout.add_lwpolyline([(x * k, y * k) for x, y in pts], close=bool(w.get('fechada')),
                                      dxfattribs={'layer': L_PAREDE}))
            cnt['paredes'] += 1
        except Exception as ex:
            warns.append(f'Parede {i} ignorada: {ex}')

    for i, a in enumerate(data.get('ambientes') or [], 1):
        try:
            x, y = _num(a.get('x'), f'ambiente {i}'), _num(a.get('y'), f'ambiente {i}')
            nome = str(a.get('nome', ''))[:60]
            if nome:
                reg(layout.add_text(nome, dxfattribs={'layer': 'ELE-TEXTO', 'height': th * 1.4,
                                                      'insert': (x * k, y * k)}))
                cnt['ambientes'] += 1
        except Exception as ex:
            warns.append(f'Ambiente {i} ignorado: {ex}')

    for i, s in enumerate(data.get('simbolos') or [], 1):
        try:
            tipo = s.get('tipo')
            if tipo not in E.SYMBOLS:
                raise ValueError(f'tipo desconhecido: {tipo!r}')
            x, y = _num(s.get('x'), f'símbolo {i}'), _num(s.get('y'), f'símbolo {i}')
            rot = _num(s.get('rotacao', 0), f'símbolo {i}')
            reg(E.insert_symbol(doc, layout, tipo, (x * k, y * k), sym_scale, rot))
            cnt['simbolos'] += 1
            tag = s.get('circuito')
            if tag:
                reg(layout.add_text(str(tag)[:20], dxfattribs={'layer': 'ELE-TEXTO', 'height': th * 0.8,
                                                                'insert': (x * k + sym_scale * 1.3, y * k - sym_scale * 1.6)}))
        except Exception as ex:
            warns.append(f'Símbolo {i} ignorado: {ex}')

    for i, d in enumerate(data.get('eletrodutos') or [], 1):
        try:
            pts = [_pt(p, f'eletroduto {i}') for p in d.get('pontos', [])]
            if len(pts) < 2:
                raise ValueError('precisa de 2 pontos ou mais')
            layer = E.LAYER_ELETRODUTO_PISO if d.get('tipo') == 'piso' else E.LAYER_ELETRODUTO_TETO
            reg(layout.add_lwpolyline([(x * k, y * k) for x, y in pts], dxfattribs={'layer': layer}))
            cnt['eletrodutos'] += 1
        except Exception as ex:
            warns.append(f'Eletroduto {i} ignorado: {ex}')

    return {'contagem': cnt, 'avisos': warns, 'circuitos': read_circuits(data, warns)}


def export(layout, unit_mm, circuits, nome='Projeto'):
    """Dicionário no mesmo formato, com os símbolos do desenho e os circuitos."""
    unit = {1.0: 'mm', 10.0: 'cm', 1000.0: 'm'}.get(round(unit_mm, 6))
    k = 1.0
    if unit is None:   # unidade fora do padrão: converte para metros
        unit, k = 'm', unit_mm / 1000.0
    simbolos = []
    for e in layout:
        if e.dxftype() == 'INSERT':
            sid = E.symbol_id(e.dxf.name)
            if sid:
                p = e.dxf.insert
                simbolos.append({'tipo': sid, 'x': round(p.x * k, 4), 'y': round(p.y * k, 4),
                                 'rotacao': round(e.dxf.get('rotation', 0) or 0, 3)})
    return {'formato': 'electracad-projeto', 'versao': 1, 'unidade': unit, 'nome': nome, 'simbolos': simbolos,
            'circuitos': [{'nome': c['nome'], 'tipo': c['tipo'], 'tensao': c['v'], 'fases': c['fases'],
                           'potencia_va': c['va']} for c in circuits]}


def dumps(d):
    return json.dumps(d, ensure_ascii=False, indent=2)
