import importlib.util
import pathlib
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date

repo_root = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('app', str(repo_root / 'app.py'))
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

engine = app.engine
Pago = app.Pago
Prestamo = app.Prestamo

s = Session(bind=engine)

print('Pagos en la base de datos:')
for p in s.query(Pago).order_by(Pago.fecha).all():
    print(p.id, p.fecha, p.prestamo_id, p.capital_pagado, p.interes_pagado, p.monto)

mes_actual = date.today().strftime('%Y-%m')
print('\nMes actual:', mes_actual)
total_mes = s.query(func.sum(Pago.monto)).filter(func.substr(Pago.fecha, 1, 7) == mes_actual).scalar() or 0
print('Total recaudado este mes (según DB):', total_mes)

s.close()

# Buscar préstamos con cliente que contenga 'vivi'
from sqlalchemy import or_
s = Session(bind=engine)
print('\nPréstamos (cliente):')
for pr in s.query(Prestamo).all():
    print(pr.id, pr.cliente, pr.capital_inicial, pr.capital_actual, pr.fecha_inicio)

busq = 'vivi'
matches = s.query(Prestamo).filter(func.lower(Prestamo.cliente).like(f"%{busq}%")).all()
print(f"\nPréstamos que contienen '{busq}':")
for m in matches:
    print(m.id, m.cliente)

s.close()