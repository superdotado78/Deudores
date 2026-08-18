import sys
import app
from datetime import date

sys.stdout = open('debug_veterano.txt', 'w')

s = app.get_session()

print("=== ALL LOANS AFTER FIX ===")
print(f"Hoy: {date.today()}")
print()

for pr in s.query(app.Prestamo).all():
    di, cr, im = app.calcular_estado(s, pr.id)
    pagos = s.query(app.Pago).filter(app.Pago.prestamo_id == pr.id).count()
    print(f"ID {pr.id:2d}: {pr.cliente:20s} | Capital: {cr:>7.2f} | Int.pend: {di:>7.2f} | Int.mens: {im:>7.2f} | Pagos: {pagos}")

s.close()
sys.stdout.close()