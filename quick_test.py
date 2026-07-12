from datetime import date
from app import get_session, Prestamo, Pago, InteresCambio, calcular_estado
import inspect

# Check if the source code has the fix
src = inspect.getsource(calcular_estado)
print("Source of calcular_estado has 'periodo > fecha_pago':", 'periodo > fecha_pago' in src)

# Check aplicar_pagos_a_intereses
from app import aplicar_pagos_a_intereses
src2 = inspect.getsource(aplicar_pagos_a_intereses)
print("Source of aplicar_pagos_a_intereses has 'periodo > fecha_pago':", 'periodo > fecha_pago' in src2)
print("Source of aplicar_pagos_a_intereses has 'for idx in range':", 'for idx in range' in src2)

# Now check Shaggy
session = get_session()
for p in session.query(Prestamo).filter(Prestamo.cliente == 'Shaggy').all():
    d, c, m = calcular_estado(session, p.id)
    print(f'ID={p.id}, capital_actual={p.capital_actual}, deuda_interes={d}, capital_real={c}')
session.close()