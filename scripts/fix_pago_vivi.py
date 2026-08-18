import importlib.util
import pathlib
from sqlalchemy.orm import Session
from datetime import date

repo_root = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('app', str(repo_root / 'app.py'))
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

engine = app.engine
Pago = app.Pago

s = Session(bind=engine)

hoy = date.today()
# Buscar el pago de hoy de vivi con monto 480
pago = s.query(Pago).filter(Pago.prestamo_id == 1, Pago.monto == 480.0, Pago.fecha == str(hoy)).first()
if not pago:
    print('No se encontró el pago esperado para vivi. Mostrando candidatos:')
    for p in s.query(Pago).filter(Pago.prestamo_id == 1).order_by(Pago.fecha.desc()).limit(5).all():
        print(p.id, p.fecha, p.capital_pagado, p.interes_pagado, p.monto)
else:
    pago.capital_pagado = 400.0
    pago.interes_pagado = 80.0
    pago.monto = 480.0
    s.commit()
    print('Pago actualizado:', pago.id)
    # Recalcular
    app.recalcular_prestamo(s, 1)
    pr = s.query(app.Prestamo).get(1)
    print('Capital actual de vivi ahora:', pr.capital_actual)

s.close()