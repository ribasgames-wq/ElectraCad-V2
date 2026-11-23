"""Tipos de linha e espessuras (lógica pura, sem Qt nem ezdxf)."""

# Padrões de traço em pixels de tela, na ordem traço, espaço, traço, espaço…
_PATTERNS = {
    'DASHED': (9, 6), 'DASHED2': (4.5, 3), 'DASHEDX2': (18, 12),
    'HIDDEN': (5, 4), 'HIDDEN2': (2.5, 2), 'HIDDENX2': (10, 8),
    'CENTER': (20, 5, 5, 5), 'CENTER2': (10, 2.5, 2.5, 2.5), 'CENTERX2': (40, 10, 10, 10),
    'DASHDOT': (10, 5, 2, 5), 'DASHDOT2': (5, 2.5, 1, 2.5), 'DASHDOTX2': (20, 10, 4, 10),
    'PHANTOM': (20, 5, 5, 5, 5, 5), 'PHANTOM2': (10, 2.5, 2.5, 2.5, 2.5, 2.5),
    'PHANTOMX2': (40, 10, 10, 10, 10, 10),
    'DOT': (2, 5), 'DOT2': (1, 2.5), 'DOTX2': (4, 10),
    'DIVIDE': (10, 5, 2, 5, 2, 5), 'DIVIDE2': (5, 2.5, 1, 2.5, 1, 2.5), 'DIVIDEX2': (20, 10, 4, 10, 4, 10),
    'BORDER': (14, 5, 14, 5, 2, 5), 'BORDER2': (7, 2.5, 7, 2.5, 1, 2.5), 'BORDERX2': (28, 10, 28, 10, 4, 10),
}

DEFAULT_LW_MM = 0.25


def resolve_linetype(entity_lt, layer_lt):
    """Nome do tipo de linha efetivo (em maiúsculas). PORCAMADA usa o da camada; PORBLOCO vira contínua."""
    lt = (entity_lt or 'BYLAYER').strip().upper()
    if lt in ('BYLAYER', ''):
        lt = (layer_lt or 'CONTINUOUS').strip().upper()
    elif lt == 'BYBLOCK':
        lt = 'CONTINUOUS'
    return lt


def dash_pattern(name):
    """Padrão de traços em pixels, ou None para linha contínua/desconhecida."""
    return _PATTERNS.get((name or '').strip().upper())


def resolve_lineweight(entity_lw, layer_lw):
    """Espessura efetiva em mm. Valores DXF: centésimos de mm; -1 por camada, -2 por bloco, -3 padrão."""
    lw = -1 if entity_lw is None else entity_lw
    if lw == -1:
        lw = -3 if layer_lw is None else layer_lw
    if lw is None or lw < 0:
        return DEFAULT_LW_MM
    return lw / 100.0


def pen_width_px(mm, px_per_mm, min_px=1.0):
    """Largura da caneta em pixels. Com px_per_mm = None (espessuras desligadas) tudo sai com min_px."""
    if px_per_mm is None:
        return min_px
    return max(min_px, mm * px_per_mm)


def scaled_pattern(name, width_px, unit=1.0):
    """Padrão para QPen.setDashPattern: o Qt mede os traços em múltiplos da largura da caneta."""
    pat = dash_pattern(name)
    if pat is None:
        return None
    w = max(width_px, 1e-6)
    return [x * unit / w for x in pat]
