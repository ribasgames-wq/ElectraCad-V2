import eletrica as E, estilo as S
# símbolos
assert len(E.SYMBOLS)==len(E.ORDER)==22
for sid in E.ORDER:
    x0,y0,x1,y1=E.extents(E.SYMBOLS[sid]['prims']); assert x1>x0 and y1>y0, sid
    assert E.SYMBOLS[sid]['layer'] in [l[0] for l in E.LAYERS], sid
assert E.symbol_id('ELEC_LUZ_TETO')=='luz_teto' and E.symbol_id('FOO') is None
# dimensionamento (NBR 5410 tab.36 B1 Cu PVC)
d=E.dimensionar('Iluminação',1000,127,'F+N'); assert d['secao']==1.5 and d['disjuntor']==10, d
d=E.dimensionar('TUG',2500,127,'F+N'); assert d['secao']==2.5 and d['disjuntor']==20 and d['iz']==24, d
d=E.dimensionar('TUE',5500,220,'F+F'); assert d['secao']==4 and d['disjuntor']==25, d   # I=25A
d=E.dimensionar('TUE',7500,220,'3F'); assert d['secao']==2.5 and d['disjuntor']==20, d    # I=19.7A, 3 cond: Iz 21
d=E.dimensionar('TUE',999999,220,'F+N'); assert d['secao'] is None and d['aviso']
# balanceamento
ck=[{'va':3000,'fases':'F+N'},{'va':2000,'fases':'F+N'},{'va':2500,'fases':'F+N'},{'va':6000,'fases':'3F'}]
f,t=E.balancear(ck); assert f[3]=='ABC' and abs(sum(t.values())-13500)<1e-6
q=E.quadro([{'num':1,'nome':'Sala','tipo':'TUG','v':127,'fases':'F+N','va':1500}],0.8)
assert q['demanda']==1200 and q['rows'][0][6]=='11,8'
assert E.fmt(2.5)=='2,5' and E.fmt(10)=='10' and E.fmt(None)=='—'
assert E.to_csv(q['header'],q['rows']).count('\n')==2
# estilo
assert S.resolve_linetype('BYLAYER','Dashed')=='DASHED' and S.resolve_linetype('BYBLOCK','x')=='CONTINUOUS'
assert S.resolve_lineweight(-1,25)==0.25 and S.resolve_lineweight(50,0)==0.5 and S.resolve_lineweight(None,-3)==0.25
assert S.dash_pattern('CONTINUOUS') is None and S.scaled_pattern('DASHED',3)==[3,2]
print('ok')
