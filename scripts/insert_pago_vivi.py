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

# Buscar prestamo de vivi
prestamo = s.query(app.Prestamo).filter(app.Prestamo.cliente == 'vivi').first()
if not prestamo:
    print('No se encontró el préstamo de vivi')
else:
    # Insertar pago de $480 hoy (todo a capital por defecto)
    hoy = date.today()
    pago = Pago(
        prestamo_id=prestamo.id,
        fecha=str(hoy),
        monto=480.0,
        interes_pagado=0.0,
        capital_pagado=480.0
    )
    s.add(pago)
    s.commit()
    # Recalcular capital
    app.recalcular_prestamo(s, prestamo.id)
    print('Pago insertado para vivi:', pago.id)

s.close()