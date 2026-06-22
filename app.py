import os
import calendar
import streamlit as st
import pandas as pd
from datetime import date

from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, func
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.engine import URL

#
# =================================================
# 🔹 BASE DE DATOS (DINÁMICA Y SEGURA)
# =================================================

database_url = os.environ.get("DATABASE_URL")

# fallback local si estás probando en tu máquina
if not database_url:
    database_url = "sqlite:///prestamos.db"

# Si la URL viene con "postgres://", SQLAlchemy requiere "postgresql://"
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

# Configuración del Engine
if database_url.startswith("sqlite"):
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False}
    )
else:
    # Lee dinámicamente cualquier URL limpia o IP directa que configures en Render
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5,
        max_overflow=10,
    )

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# =================================================
# 🔹 MODELOS
# =================================================

class Prestamo(Base):
    __tablename__ = "prestamos"

    id = Column(Integer, primary_key=True)
    cliente = Column(String)
    capital_inicial = Column(Float)
    capital_actual = Column(Float)
    tasa = Column(Float)
    fecha_inicio = Column(String)

    pagos = relationship("Pago", cascade="all, delete-orphan", backref="prestamo")


class Pago(Base):
    __tablename__ = "pagos"

    id = Column(Integer, primary_key=True)
    prestamo_id = Column(Integer, ForeignKey("prestamos.id"))
    fecha = Column(String)
    monto = Column(Float)
    interes_pagado = Column(Float)
    capital_pagado = Column(Float)


# crear tablas
Base.metadata.create_all(engine)

# =================================================
# 🔹 SESIÓN SEGURA (IMPORTANTE EN STREAMLIT)
# =================================================

def get_session():
    return SessionLocal()

# =================================================
# 🔹 FUNCIONES
# =================================================

def meses_totales(fecha_inicio):
    hoy = date.today()
    f = date.fromisoformat(fecha_inicio)
    meses = (hoy.year - f.year) * 12 + (hoy.month - f.month)
    if hoy.day < f.day:
        meses -= 1
    return max(0, meses)


def add_months(fecha, meses):
    mes = fecha.month - 1 + meses
    año = fecha.year + mes // 12
    mes = mes % 12 + 1
    dia = min(fecha.day, calendar.monthrange(año, mes)[1])
    return date(año, mes, dia)


def recalcular_prestamo(session, prestamo_id):
    p = session.get(Prestamo, prestamo_id)
    if not p:
        return

    hoy = str(date.today())

    total_capital_pagado = session.query(
        func.sum(Pago.capital_pagado)
    ).filter(
        Pago.prestamo_id == prestamo_id,
        Pago.fecha <= hoy
    ).scalar() or 0

    p.capital_actual = max(0, (p.capital_inicial or 0) - total_capital_pagado)
    session.commit()


def calcular_estado(session, prestamo_id):
    p = session.get(Prestamo, prestamo_id)
    if not p:
        return 0, 0, 0

    capital_inicial = p.capital_inicial or 0
    tasa = p.tasa or 0
    fecha_inicio = date.fromisoformat(p.fecha_inicio)

    hoy = str(date.today())

    total_capital_pagado = session.query(
        func.sum(Pago.capital_pagado)
    ).filter(
        Pago.prestamo_id == prestamo_id,
        Pago.fecha <= hoy
    ).scalar() or 0

    capital_real = max(0, capital_inicial - total_capital_pagado)
    interes_mensual = capital_real * (tasa / 100)

    meses_vencidos = meses_totales(str(fecha_inicio))

    interes_acumulado = 0
    for i in range(meses_vencidos):
        periodo = add_months(fecha_inicio, i + 1)

        capital_hasta = session.query(
            func.sum(Pago.capital_pagado)
        ).filter(
            Pago.prestamo_id == prestamo_id,
            Pago.fecha <= str(periodo)
        ).scalar() or 0

        capital_periodo = max(0, capital_inicial - capital_hasta)
        interes_acumulado += capital_periodo * (tasa / 100)

    interes_pagado = session.query(
        func.sum(Pago.interes_pagado)
    ).filter(
        Pago.prestamo_id == prestamo_id
    ).scalar() or 0

    deuda_interes = max(0, interes_acumulado - interes_pagado)

    return deuda_interes, capital_real, interes_mensual


def aplicar_pago(session, prestamo_id, monto_capital, monto_interes, fecha_pago):
    pago = Pago(
        prestamo_id=prestamo_id,
        fecha=str(fecha_pago),
        monto=monto_capital + monto_interes,
        interes_pagado=monto_interes,
        capital_pagado=monto_capital
    )

    session.add(pago)
    session.commit()

    recalcular_prestamo(session, prestamo_id)

    p = session.get(Prestamo, prestamo_id)
    if p and p.capital_actual == 0:
        session.delete(p)
        session.commit()
        return True

    return False


def eliminar_prestamo(session, prestamo_id):
    p = session.get(Prestamo, prestamo_id)
    if p:
        session.delete(p)
        session.commit()

# =================================================
# 🔹 UI STREAMLIT
# =================================================

st.set_page_config(page_title="Sistema de Préstamos", layout="wide")
st.title("💰 Sistema de Préstamos")

menu = st.sidebar.radio("Menú", [
    "Resumen",
    "Nuevo préstamo",
    "Registrar pago",
    "Editar pago",
    "Eliminar préstamo",
])

# sesión por request
session = get_session()

# ---------------- RESUMEN ----------------
if menu == "Resumen":
    prestamos = session.query(Prestamo).all()

    data = []
    for p in prestamos:
        deuda_interes, capital_real, interes_mensual = calcular_estado(session, p.id)

        data.append({
            "Cliente": p.cliente,
            "Capital": capital_real,
            "Interés mensual": interes_mensual,
            "Interés pendiente": deuda_interes,
            "Total deuda": capital_real + deuda_interes
        })

    st.dataframe(pd.DataFrame(data))

# ---------------- NUEVO PRÉSTAMO ----------------
elif menu == "Nuevo préstamo":
    cliente = st.text_input("Cliente")
    monto = st.number_input("Monto", min_value=0.0)
    tasa = st.number_input("Interés %", min_value=0.0)

    if st.button("Guardar"):
        p = Prestamo(
            cliente=cliente,
            capital_inicial=monto,
            capital_actual=monto,
            tasa=tasa,
            fecha_inicio=str(date.today())
        )
        session.add(p)
        session.commit()
        st.success("Préstamo creado")

# ---------------- REGISTRAR PAGO ----------------
elif menu == "Registrar pago":
    prestamos = session.query(Prestamo).all()

    opciones = {f"{p.cliente} (ID {p.id})": p.id for p in prestamos}

    if opciones:
        sel = st.selectbox("Préstamo", list(opciones.keys()))
        pid = opciones[sel]

        cap = st.number_input("Capital", min_value=0.0)
        intp = st.number_input("Interés", min_value=0.0)
        fecha = st.date_input("Fecha")

        if st.button("Aplicar pago"):
            eliminado = aplicar_pago(session, pid, cap, intp, fecha)
            if eliminado:
                st.success("Préstamo eliminado (pagado)")
            else:
                st.success("Pago registrado")

# ---------------- EDITAR PAGO ----------------
elif menu == "Editar pago":
    pagos = session.query(Pago).all()
    st.write(pagos)

# ---------------- ELIMINAR PRÉSTAMO ----------------
elif menu == "Eliminar préstamo":
    prestamos = session.query(Prestamo).all()

    opciones = {f"{p.cliente} (ID {p.id})": p.id for p in prestamos}

    if opciones:
        sel = st.selectbox("Eliminar", list(opciones.keys()))
        pid = opciones[sel]

        if st.button("Eliminar"):
            eliminar_prestamo(session, pid)
            st.success("Eliminado")