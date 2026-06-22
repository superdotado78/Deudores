Guía rápida: Desplegar en Render con Postgres gestionado

1) Subir repo a GitHub

2) Crear servicio de base de datos en Render
   - Render → Databases → New Database
   - Elegir Postgres, tamaño según necesidad
   - Copiar la `DATABASE_URL` proporcionada (formato: postgres://...)

3) Crear Web Service en Render
   - New → Web Service → conectar GitHub repo
   - Branch: main (o la que uses)
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `streamlit run app.py --server.address=0.0.0.0 --server.port=10000`
   - (Render asigna puerto en `PORT` env var; Streamlit soporta --server.port, pero Render mapeará. Para simplicidad ponemos 10000 o usar `PORT` env var en advanced)

4) Configurar variables de entorno
   - `DATABASE_URL` = la URL del Postgres creada en el paso 2
   - Opcional: `SECRET_KEY`, etc.

5) Ajustes y persistencia
   - La app ahora usa SQLAlchemy y leerá `DATABASE_URL`.
   - No uses SQLite en producción salvo que montes un disco persistente.

6) Migraciones / datos existentes
   - Si tienes datos en SQLite y quieres migrarlos, exporta a CSV y luego importa a Postgres o utiliza herramientas de migración.
   - He incluido `migrate_sqlite_to_postgres.py` para copiar los datos locales de `prestamos.db` a la base de datos Postgres de Render.
   - Ejemplo de uso local (antes de conectar la app en producción):
     ```bash
     export DATABASE_URL=postgres://USER:PASS@HOST:PORT/DBNAME
     python migrate_sqlite_to_postgres.py --sqlite prestamos.db --target $DATABASE_URL
     ```
   - El script crea las tablas si no existen y ajusta las secuencias en Postgres.

Notas
- Para pruebas locales usa `DATABASE_URL=sqlite:///prestamos.db`.
- Si prefieres Render detecta `PORT` env var y actualizamos `CMD` para usarla.
