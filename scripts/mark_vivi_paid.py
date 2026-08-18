import importlib.util
import pathlib
from sqlalchemy.orm import Session

repo_root = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('app', str(repo_root / 'app.py'))
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

s = Session(bind=app.engine)
pr = s.query(app.Prestamo).filter(app.Prestamo.cliente == 'vivi').first()
if not pr:
    print('No se encontró vivi')
else:
    pr.capital_actual = 0.0
    s.commit()
    print('Marcado como pagado: prestamo id', pr.id)

s.close()