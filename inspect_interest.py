import app

s = app.get_session()
print('Prestamos:')
for p in s.query(app.Prestamo).all():
    print(p.id, p.cliente, p.capital_inicial, p.capital_actual, p.tasa, p.fecha_inicio)
    print('  Cambios:')
    for c in s.query(app.InteresCambio).filter(app.InteresCambio.prestamo_id == p.id).all():
        print('   ', c.tasa, c.fecha_desde)
    print('  Pagos:')
    for pago in s.query(app.Pago).filter(app.Pago.prestamo_id == p.id).all():
        print('   ', pago.fecha, pago.monto, pago.interes_pagado, pago.capital_pagado)
    print('  Estado:', app.calcular_estado(s, p.id))
    print()
s.close()
