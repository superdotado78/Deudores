# Aplicación deudores

Pequeña aplicación en Streamlit para gestionar préstamos y pagos.

Requisitos
- Python 3.11+
- Docker (opcional para despliegue)
- Git (para versionado y push)

Ejecutar localmente (entorno virtual recomendado)
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

Variables de entorno importantes
- `DATABASE_URL`: cadena de conexión a la base de datos. Por defecto la app usa `sqlite:///prestamos.db`.
- `PORT`: puerto que Render establece para el contenedor. El `Dockerfile` respeta esta variable.

Migración de datos (SQLite -> Postgres)
Si tienes datos en `prestamos.db` y quieres pasarlos a Postgres, usa el script incluido:
```bash
# export DATABASE_URL en tu entorno con la URL de Postgres
python migrate_sqlite_to_postgres.py --sqlite prestamos.db --target "$DATABASE_URL"
```

Docker (build y run local)
```bash
docker build -t app-deudores .
docker run -e DATABASE_URL="sqlite:///prestamos.db" -p 8501:8501 app-deudores
```

Instrucciones para Git y GitHub
```bash
cd d:/AplicacionDeudores
# Inicializar repo local (si no lo has hecho)
git init
git add .
git commit -m "Initial commit: app, Dockerfile, migration script and docs"
# Crear repositorio en GitHub y luego:
git remote add origin git@github.com:TU_USUARIO/TU_REPO.git
git push -u origin main
```

Despliegue en Render (resumen)
1. Subir repo a GitHub o conectar tu repo existente a Render.
2. Crear servicio Web en Render (Docker) y un Postgres gestionado.
3. En Settings del servicio en Render, añadir la variable `DATABASE_URL` con la cadena de la base Postgres.
4. Opcional: ejecutar el script `migrate_sqlite_to_postgres.py` apuntando a la Postgres de Render para importar datos.

Si quieres, puedo preparar el commit inicial y los pasos para push remoto (pero `git` no está disponible en este entorno automatizado). 
