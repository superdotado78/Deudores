import app
from datetime import date
from unittest.mock import patch

session = app.get_session()
try:
    class FrozenDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 5)

    prestamo = app.Prestamo(
        cliente='David Fuentes',
        capital_inicial=280.0,
        capital_actual=280.0,
        tasa=20.0,
        fecha_inicio='2026-04-05',
    )
    session.add(prestamo)
    session.commit()
    session.add(app.Pago(prestamo_id=prestamo.id, fecha='2026-05-14', monto=100.0, interes_pagado=56.0, capital_pagado=44.0))
    session.add(app.Pago(prestamo_id=prestamo.id, fecha='2026-06-11', monto=80.0, interes_pagado=47.2, capital_pagado=32.8))
    session.commit()
    with patch.object(app, 'date', FrozenDate):
        print(app.calcular_estado(session, prestamo.id))
finally:
    session.close()
