"""Diagnóstico do ElectraCad: abre um DWG/DXF passo a passo e mostra onde dá problema.

Uso:   python diagnostico.py caminho/do/arquivo.dwg
       python diagnostico.py caminho/do/arquivo.dwg --lento     (registra objeto por objeto)

O relatório é gravado em  ~/ElectraCad_diagnostico.txt  a cada passo, então fica salvo mesmo que o Python caia.
"""
import sys
import os
import time
import platform
import traceback
from collections import Counter
from itertools import islice

OUT = os.path.join(os.path.expanduser('~'), 'ElectraCad_diagnostico.txt')
_f = open(OUT, 'w', encoding='utf-8')
ODA_MAC = '/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter'


def log(*a):
    s = ' '.join(str(x) for x in a)
    print(s, flush=True)
    _f.write(s + '\n')
    _f.flush()
    try:
        os.fsync(_f.fileno())
    except OSError:
        pass


def mem():
    """Pico de memória usada, em MB."""
    try:
        import resource
        r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return r / 1e6 if sys.platform == 'darwin' else r / 1e3
    except Exception:
        return -1


def geometry(e, dist, depth=0):
    """Devolve (nº de pontos, [(x, y), ...] extremos). Mesma lógica do ElectraCad, sem a interface."""
    from ezdxf import path as ezpath
    t = e.dxftype()
    if t in ('TEXT', 'ATTRIB', 'MTEXT'):
        return 0, []
    if t in ('INSERT', 'DIMENSION', 'LEADER', 'MLEADER'):
        n, ext = 0, []
        if depth < 6:
            for v in e.virtual_entities():
                a, b = geometry(v, dist, depth + 1)
                n += a
                ext += b
        return n, ext
    n, ext = 0, []
    for sp in ezpath.make_path(e).sub_paths():
        pts = list(islice(sp.flattening(dist), 20001))
        n += len(pts)
        if pts:
            xs, ys = [v.x for v in pts], [v.y for v in pts]
            ext += [(min(xs), min(ys)), (max(xs), max(ys))]
    return n, ext


def main():
    if len(sys.argv) < 2:
        print('Uso: python diagnostico.py caminho/do/arquivo.dwg')
        return
    path = os.path.expanduser(sys.argv[1].strip().strip('\'"'))
    slow = '--lento' in sys.argv
    log('=== ElectraCad: diagnóstico ===')
    log('Python', sys.version.split()[0], '|', platform.platform(), '|', platform.machine())
    try:
        import PyQt6.QtCore as qc
        log('PyQt6', qc.PYQT_VERSION_STR, '| Qt', qc.QT_VERSION_STR)
    except Exception as ex:
        log('PyQt6: ERRO ao importar:', ex)
    import ezdxf
    from ezdxf.addons import odafc
    log('ezdxf', ezdxf.__version__)
    exists = os.path.exists(path)
    log('Arquivo:', path)
    log('  existe:', exists, '| tamanho (MB):', round(os.path.getsize(path) / 1e6, 2) if exists else '-')
    if not exists:
        log('PARE: arquivo não encontrado. Dica: arraste o arquivo do Finder para dentro da janela do Terminal.')
        return

    log('ODA File Converter no local padrão:', os.path.exists(ODA_MAC))
    if os.path.exists(ODA_MAC):
        ezdxf.options.set('odafc-addon', 'unix_exec_path', ODA_MAC)
    log('odafc.is_installed():', odafc.is_installed())

    t0 = time.time()
    if path.lower().endswith('.dwg'):
        if not odafc.is_installed():
            log('PARE: o ODA File Converter não foi encontrado. Instale-o em /Applications.')
            return
        log('Etapa 1: convertendo o DWG com o ODA File Converter… (se o programa fechar aqui, o problema é a conversão)')
        doc = odafc.readfile(path)
    else:
        log('Etapa 1: lendo o DXF…')
        doc = ezdxf.readfile(path)
    log(f'   ok em {time.time() - t0:.1f}s | versão DXF {doc.dxfversion} | memória {mem():.0f} MB')

    msp = doc.modelspace()
    ents = list(msp)
    log(f'Etapa 2: {len(ents)} objetos no desenho. Por tipo:')
    for k, v in Counter(e.dxftype() for e in ents).most_common():
        log(f'   {k}: {v}')

    size = 100.0
    try:
        from ezdxf import bbox
        ext = bbox.extents(msp, fast=True)
        if ext.has_data:
            size = max(ext.size.x, ext.size.y)
            log(f'   extensão do desenho: x {ext.extmin.x:.4g} a {ext.extmax.x:.4g} | y {ext.extmin.y:.4g} a {ext.extmax.y:.4g}')
            if size > 1e9:
                log('   ATENÇÃO: o desenho tem objetos MUITO distantes (lixo no arquivo). Isso é comum e já é tratado.')
    except Exception as ex:
        log('   extensão: não foi possível calcular:', ex)
    dist = size / 4000 if size > 0 else 0.01
    log(f'Etapa 3: gerando a geometria objeto por objeto ({"lento: 1 linha por objeto" if slow else "1 linha a cada 25 objetos"}).')
    log('   Se o programa fechar aqui, a última linha "objeto N" mostra o culpado.')

    total, big, errs, t1 = 0, (0, None), {}, time.time()
    ex_min, ex_max = [1e300, 1e300], [-1e300, -1e300]
    for i, e in enumerate(ents):
        if slow or i % 25 == 0:
            log(f'   objeto {i}/{len(ents)}  tipo {e.dxftype()}  handle {e.dxf.handle}  | {mem():.0f} MB')
        try:
            n, ext = geometry(e, dist)
        except Exception as ex:
            errs.setdefault(e.dxftype(), []).append(f'{type(ex).__name__}: {ex}')
            continue
        total += n
        if n > big[0]:
            big = (n, f'{e.dxftype()} handle {e.dxf.handle}')
        for x, y in ext:
            if abs(x) < 1e12 and abs(y) < 1e12:
                ex_min[0], ex_min[1] = min(ex_min[0], x), min(ex_min[1], y)
                ex_max[0], ex_max[1] = max(ex_max[0], x), max(ex_max[1], y)
    log(f'   concluído em {time.time() - t1:.1f}s | pontos no total: {total} | memória {mem():.0f} MB')
    log(f'   maior objeto: {big[0]} pontos ({big[1]})')
    log(f'   geometria útil: x {ex_min[0]:.4g} a {ex_max[0]:.4g} | y {ex_min[1]:.4g} a {ex_max[1]:.4g}')
    if errs:
        log('Objetos que não puderam ser desenhados (normal para alguns tipos):')
        for k, v in errs.items():
            log(f'   {k}: {len(v)} | exemplo: {v[0]}')

    log('Etapa 4: teste do Qt sem janela…')
    try:
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PyQt6.QtGui import QPolygonF, QImage, QPainter, QPen
        from PyQt6.QtCore import QPointF
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)
        img = QImage(400, 300, QImage.Format.Format_ARGB32)
        p = QPainter(img)
        p.setPen(QPen())
        p.drawPolyline(QPolygonF([QPointF(0, 0), QPointF(100, 100), QPointF(200, 50)]))
        p.end()
        log('   Qt desenhou normalmente.')
    except Exception:
        log('   ERRO no teste do Qt:\n' + traceback.format_exc())
    log('=== FIM: o diagnóstico terminou sem travar. Envie o conteúdo de', OUT, '===')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        log('ERRO:\n' + traceback.format_exc())
