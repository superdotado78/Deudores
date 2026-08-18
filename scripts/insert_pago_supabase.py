import os
from datetime import date
from urllib.parse import urlparse, urlunparse, quote_plus
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, func
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

class Prestamo(Base):
    __tablename__ = 'prestamos'
    id = Column(Integer, primary_key=True)
    cliente = Column(String)
    capital_inicial = Column(Float)
    capital_actual = Column(Float)
    tasa = Column(Float)
    fecha_inicio = Column(String)

class Pago(Base):
    __tablename__ = 'pagos'
    id = Column(Integer, primary_key=True)
    prestamo_id = Column(Integer, ForeignKey('prestamos.id'))
    fecha = Column(String)
    monto = Column(Float)
    interes_pagado = Column(Float)
    capital_pagado = Column(Float)


def escape_userinfo(url):
    if '://' not in url:
        return url
    scheme, rest = url.split('://', 1)
    if '@' not in rest:
        return url
    userinfo, hostpart = rest.rsplit('@', 1)
    if ':' not in userinfo:
        return url
    user, pw = userinfo.split(':', 1)
    user = quote_plus(user)
    pw = quote_plus(pw)
    return f"{scheme}://{user}:{pw}@{hostpart}"


def normalize_database_url(url):
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)

    try:
        parsed = urlparse(url)
    except ValueError:
        return escape_userinfo(url)

    if parsed.scheme in ('postgresql', 'postgres'):
        username = parsed.username or ''
        password = parsed.password or ''
        hostname = parsed.hostname or ''
        port = f":{parsed.port}" if parsed.port else ''
        path = parsed.path or ''

        if username or password:
            userinfo = quote_plus(username)
            if password:
                userinfo += ':' + quote_plus(password)
            netloc = f"{userinfo}@{hostname}{port}"
        else:
            netloc = f"{hostname}{port}"

        return urlunparse((parsed.scheme, netloc, path, '', parsed.query or '', parsed.fragment or ''))

    return url


def main():
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise SystemExit('Debes definir la variable de entorno DATABASE_URL con tu cadena de conexión de Supabase')

    database_url = normalize_database_url(database_url)

    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={'sslmode': 'require'}
    )
    SessionLocal = sessionmaker(bind=engine)

    with SessionLocal() as session:
        prestamo = session.query(Prestamo).filter(Prestamo.cliente == 'vivi').first()
        if not prestamo:
            print('No se encontró el préstamo de vivi en Supabase')
            raise SystemExit(1)

        pago = Pago(
            prestamo_id=prestamo.id,
            fecha=str(date.today()),
            monto=480.0,
            interes_pagado=80.0,
            capital_pagado=400.0
        )
        session.add(pago)
        session.commit()
        print('Pago insertado en Supabase:', pago.id)

        total_capital = session.query(func.sum(Pago.capital_pagado)).filter(Pago.prestamo_id == prestamo.id).scalar() or 0
        prestamo.capital_actual = max(0.0, (prestamo.capital_inicial or 0.0) - total_capital)
        session.commit()
        print('Capital actual recalculado en Supabase:', prestamo.capital_actual)


if __name__ == '__main__':
    main()
