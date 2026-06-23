import os
import calendar
import streamlit as st
import pandas as pd
from datetime import date

from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, func
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# =================================================
# 🔹 BASE DE DATOS
# =================================================

database_url = os.environ.get("DATABASE_URL")

if not database_url:
    database_url = "sqlite:///prestamos.db"

if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

# Engine
if database_url.startswith("sqlite"):
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"sslmode": "require"},
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


# Crear tablas (protegido)
try:
    Base.metadata.create_all(engine)
except Exception as e:
    print("Error DB:", e)


# =================================================
# 🔹 FUNCIONES
# =================================================

def get_session():
    return SessionLocal()


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


def prox_fecha_pago(fecha_inicio):
    """Calcula la próxima fecha de pago basada en la fecha de inicio."""
    fecha_inicio_date = date.fromisoformat(fecha_inicio)
    meses = meses_totales(fecha_inicio)
    prox = add_months(fecha_inicio_date, meses)
    hoy = date.today()
    if prox < hoy:
        prox = add_months(fecha_inicio_date, meses + 1)
    return prox


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

    total_capital_pagado = session.query(
        func.sum(Pago.capital_pagado)
    ).filter(
        Pago.prestamo_id == prestamo_id
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
# 🔹 UI
# =================================================

st.set_page_config(page_title="Sistema de Préstamos", layout="wide")
st.title("💰 Sistema de Préstamos")

menu = st.sidebar.radio("Menú", [
    "Resumen",
    "Nuevo préstamo",
    "Registrar pago",
    "Historial mensual",
    "Editar préstamo",
    "Editar pago",
    "Eliminar préstamo",
])

session = get_session()

# =================================================
# ✅ RESUMEN (CON MÉTRICAS)
# =================================================

if menu == "Resumen":
    prestamos = session.query(Prestamo).all()

    # Calcular próxima fecha de pago para cada préstamo y ordenar
    prestamos_con_fecha = []
    for p in prestamos:
        prox_fecha = prox_fecha_pago(p.fecha_inicio)
        prestamos_con_fecha.append((p, prox_fecha))

    # Ordenar por fecha de pago (más próximo primero)
    prestamos_con_fecha.sort(key=lambda x: x[1])

    data = []
    total_deuda = 0
    total_interes_mensual = 0

    hoy = date.today()
    mes_actual = hoy.strftime("%Y-%m")

    for p, prox_fecha in prestamos_con_fecha:
        deuda_interes, capital_real, interes_mensual = calcular_estado(session, p.id)

        data.append({
            "Cliente": p.cliente,
            "Fecha de pago": prox_fecha.strftime("%Y-%m-%d"),
            "Capital": round(capital_real, 2),
            "Interés mensual": round(interes_mensual, 2),
            "Interés pendiente": round(deuda_interes, 2),
            "Total deuda": round(capital_real + deuda_interes, 2)
        })

        total_deuda += capital_real + deuda_interes
        total_interes_mensual += interes_mensual

    total_recaudado_mes = session.query(func.sum(Pago.monto)).filter(
        func.substr(Pago.fecha, 1, 7) == mes_actual
    ).scalar() or 0

    col1, col2, col3 = st.columns(3)

    col1.metric("💵 Ganancia mensual", f"${total_interes_mensual:,.2f}")
    col2.metric("📥 Recaudado este mes", f"${total_recaudado_mes:,.2f}")
    col3.metric("📊 Deuda total", f"${total_deuda:,.2f}")

    if data:
        df = pd.DataFrame(data)
        df.insert(0, "#", range(1, len(df) + 1))
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No hay préstamos registrados aún.")


# =================================================
# NUEVO PRÉSTAMO
# =================================================

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


# =================================================
# REGISTRAR PAGO
# =================================================

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
                st.success("Préstamo eliminado")
            else:
                st.success("Pago registrado")


# =================================================
# HISTORIAL MENSUAL
# =================================================

elif menu == "Historial mensual":
    st.header("📊 Historial de recaudos por mes")

    # Consultar todos los pagos agrupados por mes
    resultados = session.query(
        func.substr(Pago.fecha, 1, 7).label('mes'),
        func.sum(Pago.monto).label('total')
    ).group_by(func.substr(Pago.fecha, 1, 7)).order_by(func.substr(Pago.fecha, 1, 7)).all()

    if resultados:
        datos_historial = []
        total_general = 0

        meses_es = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 
                    'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']

        for mes_key, total in resultados:
            total = total or 0
            total_general += total

            # Convertir 'YYYY-MM' a formato legible
            partes = str(mes_key).split('-')
            if len(partes) == 2:
                año, mes_num = partes
                mes_nombre = meses_es[int(mes_num) - 1]
                mes_formateado = f"{mes_nombre.capitalize()} {año}"
            else:
                mes_formateado = mes_key

            datos_historial.append({
                "#": len(datos_historial) + 1,
                "Mes": mes_formateado,
                "Total recaudado": round(total, 2)
            })

        df_historial = pd.DataFrame(datos_historial)
        st.dataframe(df_historial, use_container_width=True, hide_index=True)

        st.divider()
        st.metric("💰 Total acumulado desde el inicio", f"${total_general:,.2f}")

        # Detalle por mes
        st.subheader("📋 Detalle de pagos por mes")
        mes_seleccionado = st.selectbox(
            "Selecciona un mes para ver detalles:",
            [r[0] for r in resultados],
            format_func=lambda x: f"{meses_es[int(str(x).split('-')[1]) - 1].capitalize()} {str(x).split('-')[0]}"
        )

        if mes_seleccionado:
            pagos_mes = session.query(
                Pago.id,
                Pago.fecha,
                Prestamo.cliente,
                Pago.capital_pagado,
                Pago.interes_pagado,
                Pago.monto
            ).join(Prestamo).filter(
                func.substr(Pago.fecha, 1, 7) == mes_seleccionado
            ).order_by(Pago.fecha).all()

            if pagos_mes:
                datos_detalle = []
                for pago_id, fecha, cliente, capital, interes, monto in pagos_mes:
                    datos_detalle.append({
                        "#": len(datos_detalle) + 1,
                        "Pago ID": pago_id,
                        "Fecha": fecha,
                        "Cliente": cliente,
                        "Capital": round(capital, 2),
                        "Interés": round(interes, 2),
                        "Total": round(monto, 2)
                    })

                df_detalle = pd.DataFrame(datos_detalle)
                st.dataframe(df_detalle, use_container_width=True, hide_index=True)
            else:
                st.info("No hay pagos en este mes")
    else:
        st.info("No hay pagos registrados aún")


# =================================================
# EDITAR PRÉSTAMO
# =================================================

elif menu == "Editar préstamo":
    st.header("✏️ Editar préstamo")
    prestamos = session.query(Prestamo).all()

    if prestamos:
        opciones = {f"{p.cliente} (ID {p.id})": p for p in prestamos}
        seleccion = st.selectbox("Seleccionar préstamo", list(opciones.keys()))
        prestamo = opciones[seleccion]

        deuda_interes, capital_real, interes_mensual = calcular_estado(session, prestamo.id)

        st.info(f"""
        **Estado actual:**
        - Capital actual: ${capital_real:,.2f}
        - Interés mensual: ${interes_mensual:,.2f}
        - Interés pendiente: ${deuda_interes:,.2f}
        """)

        col1, col2 = st.columns(2)
        with col1:
            nuevo_cliente = st.text_input("Cliente", value=prestamo.cliente)
            nuevo_capital = st.number_input("Capital actual", value=prestamo.capital_actual or 0.0, min_value=0.0, step=0.01)
        with col2:
            nueva_tasa = st.number_input("Interés %", value=prestamo.tasa or 0.0, min_value=0.0, step=0.01)
            nueva_fecha = st.date_input("Fecha de inicio", value=date.fromisoformat(prestamo.fecha_inicio))

        if st.button("Guardar cambios"):
            prestamo.cliente = nuevo_cliente
            prestamo.capital_actual = nuevo_capital
            prestamo.tasa = nueva_tasa
            prestamo.fecha_inicio = str(nueva_fecha)
            session.commit()
            st.success("Préstamo actualizado correctamente")
    else:
        st.info("No hay préstamos para editar")


# =================================================
# EDITAR PAGO
# =================================================

elif menu == "Editar pago":
    st.header("✏️ Editar pago")
    pagos = session.query(Pago).join(Prestamo).order_by(Pago.fecha.desc()).all()

    if pagos:
        opciones = {f"Pago {p.id} | {p.prestamo.cliente} | {p.fecha} | ${p.monto:.2f}": p for p in pagos}
        seleccion = st.selectbox("Seleccionar pago", list(opciones.keys()))
        pago = opciones[seleccion]

        fecha = st.date_input("Fecha", value=date.fromisoformat(pago.fecha))
        capital_pagado = st.number_input("Capital pagado", value=pago.capital_pagado or 0.0, min_value=0.0, step=0.01)
        interes_pagado = st.number_input("Interés pagado", value=pago.interes_pagado or 0.0, min_value=0.0, step=0.01)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Guardar cambios"):
                pago.fecha = str(fecha)
                pago.capital_pagado = capital_pagado
                pago.interes_pagado = interes_pagado
                pago.monto = capital_pagado + interes_pagado
                session.commit()
                recalcular_prestamo(session, pago.prestamo_id)
                st.success("Pago actualizado correctamente")
        with col2:
            if st.button("Eliminar pago", type="secondary"):
                prestamo_id = pago.prestamo_id
                session.delete(pago)
                session.commit()
                recalcular_prestamo(session, prestamo_id)
                st.success("Pago eliminado correctamente")
    else:
        st.info("No hay pagos registrados")


# =================================================
# ELIMINAR
# =================================================

elif menu == "Eliminar préstamo":
    prestamos = session.query(Prestamo).all()

    opciones = {f"{p.cliente} (ID {p.id})": p.id for p in prestamos}

    if opciones:
        sel = st.selectbox("Eliminar", list(opciones.keys()))
        pid = opciones[sel]

        if st.button("Eliminar"):
            eliminar_prestamo(session, pid)
            st.success("Eliminado")
    else:
        st.info("No hay préstamos para eliminar")