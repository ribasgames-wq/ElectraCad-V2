"""Testes da geometria. Rode:  python3 tests_geom.py"""
import math
import geom as g


def close(a, b, tol=1e-9):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


# interseções
r = g.seg_intersect((0, 0), (10, 0), (5, -5), (5, 5))
assert r and close(r[:2], (5, 0)) and abs(r[2] - .5) < 1e-12 and abs(r[3] - .5) < 1e-12
assert g.seg_intersect((0, 0), (1, 0), (2, -1), (2, 1)) is None          # não alcança
assert g.seg_intersect((0, 0), (1, 0), (0, 1), (1, 1)) is None          # paralelas
assert close(g.line_intersect((0, 0), (1, 0), (2, -1), (2, 1)), (2, 0))  # retas infinitas
assert g.line_intersect((0, 0), (1, 0), (0, 1), (1, 1)) is None
assert abs(g.ray_seg_intersect((0, 0), (1, 0), (5, -1), (5, 1)) - 5) < 1e-12
assert g.ray_seg_intersect((0, 0), (-1, 0), (5, -1), (5, 1)) is None     # atrás do raio

# pé da perpendicular, distância
f = g.foot((3, 4), (0, 0), (10, 0))
assert close(f, (3, 0, .3))
assert abs(g.seg_point_dist((15, 0), (0, 0), (10, 0)) - 5) < 1e-12

# entrada de pontos
assert g.parse_point('1,2') == (1, 2)
assert g.parse_point('-1.5;2') == (-1.5, 2)
assert g.parse_point('@3,4', (10, 10)) == (13, 14)
p = g.parse_point('@10<90', (5, 5))
assert close(p, (5, 15), 1e-9)
assert g.parse_point('10') is None and g.parse_point('abc') is None

# ortogonal e polar
assert g.ortho_point((0, 0), (10, 3)) == (10, 0)
assert g.ortho_point((0, 0), (3, -10)) == (0, -10)
q = g.polar_point((0, 0), (10, 0.5), 15)                 # ~2,9° -> trava em 0°
assert close(q, (math.hypot(10, .5), 0), 1e-9)
q = g.polar_point((0, 0), (10, 10.6), 15)                # ~46,7° -> trava em 45°
assert abs(math.degrees(math.atan2(q[1], q[0])) - 45) < 1e-9
assert g.polar_point((0, 0), (10, 4), 15) == (10, 4)     # 21,8° está a 6,8° do múltiplo mais próximo -> livre
q = g.polar_point((0, 0), (10, 5), 15)                   # 26,6° está a 3,4° de 30° -> trava em 30°
assert abs(math.degrees(math.atan2(q[1], q[0])) - 30) < 1e-9

# arcos
c = g.circle_3pts((1, 0), (0, 1), (-1, 0))
assert close(c, (0, 0, 1), 1e-9)
assert g.circle_3pts((0, 0), (1, 1), (2, 2)) is None
a = g.arc_from_3pts((1, 0), (0, 1), (-1, 0))             # anti-horário, 0° a 180°
assert abs(a[3] - 0) < 1e-9 and abs(a[4] - 180) < 1e-9
a = g.arc_from_3pts((1, 0), (0, -1), (-1, 0))            # horário passando por baixo: vira 180° -> 360°
assert abs(a[3] - 180) < 1e-9 and abs(a[4] - 0) < 1e-9
pts = g.arc_points(0, 0, 1, 180, 0)                      # arco de baixo (180 -> 360)
assert all(p[1] <= 1e-9 for p in pts) and close(pts[0], (-1, 0), 1e-9) and close(pts[-1], (1, 0), 1e-9)

# deslocar
na, nb = g.offset_line((0, 0), (10, 0), 2, (5, 7))
assert na == (0, 2) and nb == (10, 2)
na, nb = g.offset_line((0, 0), (10, 0), 2, (5, -7))
assert na == (0, -2) and nb == (10, -2)
sq = [(0, 0), (10, 0), (10, 10), (0, 10)]                # anti-horário: esquerda = dentro
inner = g.offset_polyline(sq, 1, closed=True)
assert all(close(a, b) for a, b in zip(inner, [(1, 1), (9, 1), (9, 9), (1, 9)]))
outer = g.offset_polyline(sq, -1, closed=True)
assert all(close(a, b) for a, b in zip(outer, [(-1, -1), (11, -1), (11, 11), (-1, 11)]))
op = g.offset_polyline([(0, 0), (10, 0), (10, 10)], 1)   # aberta, curva à esquerda
assert all(close(a, b) for a, b in zip(op, [(0, 1), (9, 1), (9, 10)]))
assert g.side_of_polyline(sq, True, (5, 5)) == 1 and g.side_of_polyline(sq, True, (5, -5)) == -1

# aparar
cut = [((3, -1), (3, 1)), ((7, -1), (7, 1))]
assert g.trim_line((0, 0), (10, 0), cut, (5, 0)) == [((0, 0), (3.0, 0.0)), ((7.0, 0.0), (10, 0))]
assert g.trim_line((0, 0), (10, 0), cut, (1, 0)) == [((3.0, 0.0), (10, 0))]
assert g.trim_line((0, 0), (10, 0), cut, (9, 0)) == [((0, 0), (7.0, 0.0))]
assert g.trim_line((0, 0), (10, 0), [((20, -1), (20, 1))], (5, 0)) is None

# estender
edges = [((12, -5), (12, 5)), ((20, -5), (20, 5))]
assert close(g.extend_line((0, 0), (10, 0), 1, edges), (12, 0))
assert g.extend_line((0, 0), (10, 0), 0, edges) is None
assert close(g.extend_line((0, 0), (10, 0), 0, [((-3, -1), (-3, 1))]), (-3, 0))

# canto (fillet raio 0)
n1, n2 = g.fillet_corner((0, 0), (8, 0), (10, -5), (10, 5), (2, 0), (10, 3))
assert close(n1[1], (10, 0)) and n1[0] == (0, 0)         # primeira linha estendida até a segunda
assert close(n2[0], (10, 0)) and n2[1] == (10, 5)        # segunda mantém o lado clicado (cima)
assert g.fillet_corner((0, 0), (1, 0), (0, 1), (1, 1), (0, 0), (0, 1)) is None

# espelho
assert close(g.mirror_point((3, 4), (0, 0), (10, 0)), (3, -4))
assert close(g.mirror_point((3, 4), (0, 0), (1, 1)), (4, 3))

# recorte de segmentos (evita coordenadas gigantes na tela)
assert g.clip_segment((-1e20, 5), (1e20, 5), 0, 0, 10, 10) == ((0.0, 5.0), (10.0, 5.0))
assert g.clip_segment((2, 2), (4, 4), 0, 0, 10, 10) == ((2.0, 2.0), (4.0, 4.0))   # já dentro
assert g.clip_segment((20, 0), (30, 10), 0, 0, 10, 10) is None                     # todo fora
assert g.clip_segment((5, -5), (5, 15), 0, 0, 10, 10) == ((5.0, 0.0), (5.0, 10.0)) # vertical
assert g.clip_segment((0, 20), (20, 0), 0, 0, 10, 10) is not None                  # diagonal cortando o canto

print('Todos os testes de geometria passaram.')
