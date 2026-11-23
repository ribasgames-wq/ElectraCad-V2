"""Geometria 2D pura (sem Qt nem ezdxf) usada pelo ElectraCad. Pontos são tuplas (x, y)."""
import math
import re

EPS = 1e-9


def dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def seg_point_dist(p, a, b):
    """Distância do ponto p ao segmento ab."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    l = dx * dx + dy * dy
    t = 0.0 if l == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def foot(p, a, b):
    """Pé da perpendicular de p sobre a reta ab: (x, y, t), com t=0 em a e t=1 em b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    l = dx * dx + dy * dy
    if l == 0:
        return (a[0], a[1], 0.0)
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l
    return (a[0] + t * dx, a[1] + t * dy, t)


def seg_intersect(a, b, c, d):
    """Interseção dos segmentos ab e cd: (x, y, t, u) ou None. t é o parâmetro em ab, u em cd."""
    r = (b[0] - a[0], b[1] - a[1])
    s = (d[0] - c[0], d[1] - c[1])
    den = cross(r, s)
    if abs(den) <= 1e-12 * math.hypot(*r) * math.hypot(*s):
        return None
    qp = (c[0] - a[0], c[1] - a[1])
    t = cross(qp, s) / den
    u = cross(qp, r) / den
    if -EPS <= t <= 1 + EPS and -EPS <= u <= 1 + EPS:
        return (a[0] + t * r[0], a[1] + t * r[1], t, u)
    return None


def line_intersect(a, b, c, d):
    """Interseção das retas infinitas ab e cd, ou None se paralelas."""
    r = (b[0] - a[0], b[1] - a[1])
    s = (d[0] - c[0], d[1] - c[1])
    den = cross(r, s)
    if abs(den) <= 1e-12 * math.hypot(*r) * math.hypot(*s):
        return None
    t = cross((c[0] - a[0], c[1] - a[1]), s) / den
    return (a[0] + t * r[0], a[1] + t * r[1])


def ray_seg_intersect(o, dv, c, d):
    """Raio o + s*dv (s > 0) contra o segmento cd. Retorna s ou None."""
    sv = (d[0] - c[0], d[1] - c[1])
    den = cross(dv, sv)
    if abs(den) <= 1e-12 * math.hypot(*dv) * math.hypot(*sv):
        return None
    co = (c[0] - o[0], c[1] - o[1])
    s = cross(co, sv) / den
    u = cross(co, dv) / den
    if s > EPS and -EPS <= u <= 1 + EPS:
        return s
    return None


# ---------- entrada de pontos e restrições ----------
_NUM = r'[-+]?(?:\d+\.?\d*|\.\d+)'


def parse_point(text, last=(0.0, 0.0)):
    """Lê 'x,y', '@dx,dy', 'dist<ângulo' ou '@dist<ângulo'. Retorna (x, y) ou None."""
    t = text.replace(' ', '')
    rel = t.startswith('@')
    if rel:
        t = t[1:]
    m = re.fullmatch(rf'({_NUM})[,;]({_NUM})', t)
    if m:
        x, y = float(m[1]), float(m[2])
    else:
        m = re.fullmatch(rf'({_NUM})<({_NUM})', t)
        if not m:
            return None
        d, a = float(m[1]), math.radians(float(m[2]))
        x, y = d * math.cos(a), d * math.sin(a)
    if rel:
        x, y = x + last[0], y + last[1]
    return (x, y)


def ortho_point(o, p):
    """Força p a ficar na horizontal ou vertical de o."""
    if abs(p[0] - o[0]) >= abs(p[1] - o[1]):
        return (p[0], o[1])
    return (o[0], p[1])


def polar_point(o, p, inc=15.0, tol=None):
    """Se o ângulo de o→p estiver perto de um múltiplo de inc graus, alinha p nele."""
    dx, dy = p[0] - o[0], p[1] - o[1]
    d = math.hypot(dx, dy)
    if d == 0:
        return p
    ang = math.degrees(math.atan2(dy, dx))
    near = round(ang / inc) * inc
    if tol is None:
        tol = min(5.0, inc / 2)
    if abs(ang - near) <= tol:
        a = math.radians(near)
        return (o[0] + d * math.cos(a), o[1] + d * math.sin(a))
    return p


# ---------- arcos ----------
def circle_3pts(p1, p2, p3):
    """Círculo por três pontos: (cx, cy, r) ou None se colineares."""
    v1 = (p2[0] - p1[0], p2[1] - p1[1])
    v2 = (p3[0] - p1[0], p3[1] - p1[1])
    if abs(cross(v1, v2)) <= 1e-9 * math.hypot(*v1) * math.hypot(*v2):
        return None
    ax, ay = p1
    bx, by = p2
    cx, cy = p3
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    return (ux, uy, math.hypot(ax - ux, ay - uy))


def arc_from_3pts(p1, p2, p3):
    """Arco que sai de p1, passa por p2 e termina em p3: (cx, cy, r, ang_ini, ang_fim) em graus, anti-horário."""
    c = circle_3pts(p1, p2, p3)
    if c is None:
        return None
    ux, uy, r = c
    ang = lambda p: math.degrees(math.atan2(p[1] - uy, p[0] - ux)) % 360
    ccw = cross((p2[0] - p1[0], p2[1] - p1[1]), (p3[0] - p2[0], p3[1] - p2[1])) > 0
    a1, a3 = ang(p1), ang(p3)
    return (ux, uy, r, a1, a3) if ccw else (ux, uy, r, a3, a1)


def arc_points(cx, cy, r, start, end, n=48):
    sweep = (end - start) % 360 or 360.0
    return [(cx + r * math.cos(math.radians(start + sweep * i / n)),
             cy + r * math.sin(math.radians(start + sweep * i / n))) for i in range(n + 1)]


# ---------- deslocar ----------
def offset_line(a, b, d, side_pt):
    """Linha ab deslocada d para o lado onde está side_pt."""
    L = dist(a, b)
    nx, ny = -(b[1] - a[1]) / L, (b[0] - a[0]) / L
    sign = 1 if cross((b[0] - a[0], b[1] - a[1]), (side_pt[0] - a[0], side_pt[1] - a[1])) >= 0 else -1
    return ((a[0] + nx * d * sign, a[1] + ny * d * sign), (b[0] + nx * d * sign, b[1] + ny * d * sign))


def side_of_polyline(pts, closed, p):
    """+1 se p está à esquerda do trecho mais próximo da polilinha, -1 se à direita."""
    n = len(pts)
    best, bd = None, 1e300
    for i in range(n if closed else n - 1):
        a, b = pts[i], pts[(i + 1) % n]
        if a == b:
            continue
        dd = seg_point_dist(p, a, b)
        if dd < bd:
            bd, best = dd, (a, b)
    if best is None:
        return 1
    a, b = best
    return 1 if cross((b[0] - a[0], b[1] - a[1]), (p[0] - a[0], p[1] - a[1])) >= 0 else -1


def _join(s1, s2):
    x = line_intersect(s1[0], s1[1], s2[0], s2[1])
    return x if x is not None else s1[1]


def offset_polyline(pts, d, closed=False):
    """Desloca uma polilinha de trechos retos: d > 0 para a esquerda, d < 0 para a direita (junções em esquadro)."""
    P = [pts[0]]
    for q in pts[1:]:
        if dist(q, P[-1]) > EPS:
            P.append(q)
    if closed and len(P) > 1 and dist(P[0], P[-1]) <= EPS:
        P.pop()
    n = len(P)
    if n < 2:
        return list(P)
    m = n if closed else n - 1
    segs = []
    for i in range(m):
        a, b = P[i], P[(i + 1) % n]
        L = dist(a, b)
        nx, ny = -(b[1] - a[1]) / L, (b[0] - a[0]) / L
        segs.append(((a[0] + nx * d, a[1] + ny * d), (b[0] + nx * d, b[1] + ny * d)))
    if closed:
        return [_join(segs[i - 1], segs[i]) for i in range(m)]
    out = [segs[0][0]]
    out += [_join(segs[i - 1], segs[i]) for i in range(1, m)]
    out.append(segs[-1][1])
    return out


# ---------- aparar, estender, canto ----------
def trim_line(a, b, cutters, pick):
    """Apara a linha ab no trecho clicado em pick, entre as interseções com os segmentos cutters.
    Retorna a lista de pedaços que sobram [(p, q), ...], ou None se não há interseção."""
    ts = []
    for c, d in cutters:
        r = seg_intersect(a, b, c, d)
        if r is not None and EPS < r[2] < 1 - EPS:
            ts.append(r[2])
    if not ts:
        return None
    tp = max(0.0, min(1.0, foot(pick, a, b)[2]))
    lo = max([t for t in ts if t <= tp], default=0.0)
    hi = min([t for t in ts if t > tp], default=1.0)
    pt = lambda t: (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
    out = []
    if lo > EPS:
        out.append((a, pt(lo)))
    if hi < 1 - EPS:
        out.append((pt(hi), b))
    return out


def extend_line(a, b, end, cutters):
    """Estende a ponta `end` (0 = a, 1 = b) da linha ab até o primeiro segmento em cutters. Retorna o novo ponto ou None."""
    o, other = (a, b) if end == 0 else (b, a)
    dv = (o[0] - other[0], o[1] - other[1])
    if dv == (0, 0):
        return None
    best = None
    for c, d in cutters:
        s = ray_seg_intersect(o, dv, c, d)
        if s is not None and (best is None or s < best):
            best = s
    return None if best is None else (o[0] + best * dv[0], o[1] + best * dv[1])


def fillet_corner(a1, b1, a2, b2, pick1, pick2):
    """Fecha o canto entre duas linhas (raio 0), mantendo o lado clicado. Retorna ((p,q),(p,q)) ou None."""
    x = line_intersect(a1, b1, a2, b2)
    if x is None:
        return None

    def fix(a, b, pick):
        tx = foot(x, a, b)[2]
        tp = foot(pick, a, b)[2]
        return (x, b) if tp > tx else (a, x)

    return fix(a1, b1, pick1), fix(a2, b2, pick2)


def clip_segment(a, b, xmin, ymin, xmax, ymax):
    """Recorta o segmento ab pelo retângulo (Liang-Barsky). Retorna (p, q) ou None se fica todo fora."""
    x0, y0 = a
    dx, dy = b[0] - x0, b[1] - y0
    t0, t1, e0, e1 = 0.0, 1.0, None, None   # e0/e1: borda que limitou cada ponta (0 esq, 1 dir, 2 baixo, 3 cima)
    for i, (pp, qq) in enumerate(((-dx, x0 - xmin), (dx, xmax - x0), (-dy, y0 - ymin), (dy, ymax - y0))):
        if pp == 0:
            if qq < 0:
                return None
        else:
            t = qq / pp
            if pp < 0:
                if t > t1:
                    return None
                if t > t0:
                    t0, e0 = t, i
            else:
                if t < t0:
                    return None
                if t < t1:
                    t1, e1 = t, i

    def point(t, edge):
        x, y = x0 + t * dx, y0 + t * dy
        if edge is not None:  # fixa a coordenada exatamente na borda (evita erro com números gigantes)
            if edge == 0: x = xmin
            elif edge == 1: x = xmax
            elif edge == 2: y = ymin
            else: y = ymax
        return (x, y)
    return (point(t0, e0), point(t1, e1))


def mirror_point(p, a, b):
    """Reflexo do ponto p na reta ab."""
    f = foot(p, a, b)
    return (2 * f[0] - p[0], 2 * f[1] - p[1])
