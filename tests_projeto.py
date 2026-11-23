import json, types
import eletrica as E, folha as F, projeto_io as P
class NS(dict):
    __getattr__=dict.get
class Ent:
    def __init__(s,t,**d): s.t=t; s.dxf=NS(d)
    def dxftype(s): return s.t
class Lay(list):
    def _a(s,t,attr,**k): e=Ent(t,**(attr or {}),**k); s.append(e); return e
    def add_line(s,a,b,dxfattribs=None): return s._a('LINE',dxfattribs,start=a,end=b)
    def add_lwpolyline(s,pts,close=False,dxfattribs=None): return s._a('LWPOLYLINE',dxfattribs,pts=pts,close=close)
    def add_text(s,t,dxfattribs=None): return s._a('TEXT',dxfattribs,text=t)
    def add_blockref(s,n,pos,dxfattribs=None): return s._a('INSERT',dxfattribs,name=n,insert=types.SimpleNamespace(x=pos[0],y=pos[1]))
class Blk(Lay):
    add_circle=lambda s,*a,**k:None
class Layers(dict):
    def add(s,n,**k): s[n]=types.SimpleNamespace(color=0,dxf=NS()); return s[n]
class Doc:
    def __init__(s): s.layers=Layers(); s.linetypes=[]
    def modelspace(s): return Lay()
Doc.blocks=property(lambda s: s.__dict__.setdefault('_b',type('B',(dict,),{'new':lambda self,name: self.setdefault(name,Blk())})()))
doc=Doc(); lay=Lay()
data={'formato':'electracad-projeto','versao':1,'unidade':'m','paredes':[{'pontos':[[0,0],[10,0],[10,8],[0,8]],'fechada':True},{'pontos':[[1]]}],
 'ambientes':[{'nome':'Sala','x':1,'y':1}],'simbolos':[{'tipo':'luz_teto','x':2,'y':2,'circuito':'C1'},{'tipo':'xx','x':1,'y':1},{'tipo':'tue','x':3,'y':3,'rotacao':90}],
 'eletrodutos':[{'tipo':'piso','pontos':[[2,2],[5,2]]}],
 'circuitos':[{'nome':'Luz','tipo':'Iluminação','tensao':127,'potencia_va':600},{'nome':'ruim','potencia_va':-1}]}
d=P.parse(json.dumps(data))
r=P.apply(d,doc,lay,unit_mm=10.0,sym_scale=12.0)   # desenho em cm
c=r['contagem']; assert c=={'paredes':1,'ambientes':1,'simbolos':2,'eletrodutos':1}, c
assert len(r['avisos'])==3 and len(r['circuitos'])==1, r['avisos']
w=[e for e in lay if e.t=='LWPOLYLINE'][0]; assert w.dxf.pts[1]==(1000.0,0.0)   # 10 m = 1000 cm
ex=P.export(lay,10.0,r['circuitos']); assert ex['unidade']=='cm' and len(ex['simbolos'])==2 and ex['simbolos'][1]['rotacao']==90
assert P.parse(P.dumps(ex))['formato']=='electracad-projeto'
for bad in ('{','[]','{"formato":"x"}','{"formato":"electracad-projeto","unidade":"km"}'):
    try: P.parse(bad); assert 0
    except ValueError: pass
# folha
l2=Lay(); ents=F.draw_sheet(l2,(0,0),'A3',50,1000.0,{'Projeto':'Casa 01'})   # metros, 1:50
assert ents and any(e.dxf.get('text')=='Casa 01' for e in l2) and any(e.dxf.get('text')=='1:50' for e in l2)
big=max(p[0] for e in l2 if e.t=='LWPOLYLINE' for p in e.dxf.pts); assert abs(big-420*50/1000)<1e-9, big
import unifilar as U
ck=[{'num':1,'nome':'Iluminação','tipo':'Iluminação','v':127,'fases':'F+N','va':600},{'num':2,'nome':'Chuveiro','tipo':'TUE','v':220,'fases':'F+F','va':5500}]
q=E.quadro(ck,0.8); l3=Lay(); en=U.draw_unifilar(l3,(0,0),ck,q,1.0)
assert any(e.dxf.get('text')=='C2' for e in l3) and any(e.dxf.get('text')=='25A' for e in l3) and len(en)>25
rows=E.cable_rows(ck,q); assert rows[1][5]=='F, F, PE' and rows[1][6]=='4' and len(rows[0])==len(E.CABLE_HEADER)
print('ok')
