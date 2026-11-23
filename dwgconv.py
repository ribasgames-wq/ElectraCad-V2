"""Conversão DWG <-> DXF sem depender do ODA File Converter.

Usa o LibreDWG (dwg2dxf / dxf2dwg), que vai dentro do instalador, na pasta `bin`.
Limite do LibreDWG: lê quase todos os DWG, mas objetos muito novos podem ser ignorados; só escreve DWG R2000.
"""
import os
import shutil
import subprocess
import sys
import tempfile

WIN = sys.platform.startswith('win')


def _dirs():
    d = []
    here = os.path.dirname(os.path.abspath(__file__))
    if getattr(sys, 'frozen', False):
        base = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        d += [os.path.join(base, 'bin'), base, os.path.join(os.path.dirname(sys.executable), 'bin')]
    d += [os.path.join(here, 'bin'), os.path.expanduser('~/ElectraCad/bin')]
    if not WIN:
        d += ['/opt/homebrew/bin', '/usr/local/bin']   # Homebrew (o .app não herda o PATH do Terminal)
    return d


def find_tool(name):
    exe = name + ('.exe' if WIN else '')
    for d in _dirs():
        p = os.path.join(d, exe)
        if os.path.isfile(p):
            return p
    return shutil.which(name)


def available():
    return find_tool('dwg2dxf') is not None


def can_write():
    return find_tool('dxf2dwg') is not None


def _run(cmd, timeout=300):
    kw = {}
    if WIN:
        kw['creationflags'] = 0x08000000   # sem janela preta
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, errors='replace', **kw)


def dwg_to_dxf(src, workdir=None):
    """Converte um DWG em DXF e devolve (caminho do DXF, texto de aviso do conversor).
    Dá erro (RuntimeError) se o conversor não existir ou não produzir arquivo."""
    tool = find_tool('dwg2dxf')
    if not tool:
        raise RuntimeError('conversor de DWG não encontrado')
    out_dir = workdir or tempfile.mkdtemp(prefix='electracad_')
    out = os.path.join(out_dir, 'convertido.dxf')
    r = _run([tool, '-y', '-o', out, src])
    log = ((r.stdout or '') + (r.stderr or '')).strip()
    if not os.path.isfile(out) or os.path.getsize(out) < 100:
        raise RuntimeError('o conversor não gerou o arquivo.\n' + log[-1500:])
    return out, log


def dxf_to_dwg(src_dxf, dst_dwg):
    """Grava DWG (versão R2000) a partir de um DXF."""
    tool = find_tool('dxf2dwg')
    if not tool:
        raise RuntimeError('gravador de DWG não encontrado')
    r = _run([tool, '-y', '-o', dst_dwg, src_dxf])
    log = ((r.stdout or '') + (r.stderr or '')).strip()
    if not os.path.isfile(dst_dwg) or os.path.getsize(dst_dwg) < 100:
        raise RuntimeError('o gravador não gerou o arquivo.\n' + log[-1500:])
    return log
