"""Migra datos de SQLite local a Postgres usando SQLAlchemy.

Uso:
  SET DATABASE_URL=postgres://... (o pasa --target)
  python migrate_sqlite_to_postgres.py --sqlite prestamos.db --target $DATABASE_URL

El script:
- Crea las tablas en el destino si no existen
- Copia filas de `prestamos` y `pagos`
- Si el destino es Postgres ajusta las secuencias para `id`
"""
import argparse
import os
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Float, select, func, text


def main():
    parser = argparse.ArgumentParser(description='Migra SQLite a Postgres')
    parser.add_argument('--sqlite', dest='sqlite_path', default=os.environ.get('PRESTAMOS_DB', 'prestamos.db'))
    parser.add_argument('--target', dest='target_url', default=os.environ.get('DATABASE_URL'))
    args = parser.parse_args()

    if not args.target_url:
        print('ERROR: debes indicar --target o setear DATABASE_URL')
        return

    src_url = f'sqlite:///{args.sqlite_path}'
    print(f'Source: {src_url}')
    print(f'Target: {args.target_url}')

    src_engine = create_engine(src_url)
    dst_engine = create_engine(args.target_url)

    metadata = MetaData()

    prestamos = Table('prestamos', metadata,
                      Column('id', Integer, primary_key=True),
                      Column('cliente', String),
                      Column('capital_inicial', Float),
                      Column('capital_actual', Float),
                      Column('tasa', Float),
                      Column('fecha_inicio', String),
                      )

    pagos = Table('pagos', metadata,
                  Column('id', Integer, primary_key=True),
                  Column('prestamo_id', Integer),
                  Column('fecha', String),
                  Column('monto', Float),
                  Column('interes_pagado', Float),
                  Column('capital_pagado', Float),
                  )

    # Crear tablas en destino si no existen
    metadata.create_all(dst_engine)

    with src_engine.connect() as sconn, dst_engine.connect() as dconn:
        # Copiar prestamos
        print('Copiando prestamos...')
        result = sconn.execute(select(prestamos))
        rows = [dict(r) for r in result]
        if rows:
            dconn.execute(prestamos.insert(), rows)
            print(f'Insertadas {len(rows)} filas en prestamos')
        else:
            print('No hay filas en prestamos')

        # Copiar pagos
        print('Copiando pagos...')
        result = sconn.execute(select(pagos))
        rows = [dict(r) for r in result]
        if rows:
            dconn.execute(pagos.insert(), rows)
            print(f'Insertadas {len(rows)} filas en pagos')
        else:
            print('No hay filas en pagos')

        # Ajustar secuencias en Postgres
        if dconn.dialect.name == 'postgresql':
            print('Ajustando secuencias en Postgres...')
            for tbl in ('prestamos', 'pagos'):
                max_id = dconn.execute(text(f"SELECT COALESCE(MAX(id), 0) FROM {tbl}")).scalar()
                seq_sql = f"SELECT setval(pg_get_serial_sequence('{tbl}', 'id'), {max_id}, true);"
                dconn.execute(text(seq_sql))
            print('Secuencias ajustadas')

    print('Migración completada')


if __name__ == '__main__':
    main()
