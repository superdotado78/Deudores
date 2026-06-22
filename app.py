import calendar
import streamlit as st
import os
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, func
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import date, timedelta
import pandas as pd

# ---------------- DB ----------------
database_url = os.environ.get("DATABASE_URL", "sqlite:///prestamos.db")

# SQLAlchemy setup
engine_kwargs = {}
if database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(database_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


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


Base.metadata.create_all(engine)

session = SessionLocal()

# ---------------- FUNCIONES ----------------

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
    fecha_inicio = date.fromisoformat(fecha_inicio)
    meses = meses_totales(str(fecha_inicio))
    prox = add_months(fecha_inicio, meses)
    hoy = date.today()
    if prox < hoy:
        prox = add_months(fecha_inicio, meses + 1)
    return prox


def recalcular_prestamo(prestamo_id):
    p = session.get(Prestamo, prestamo_id)
    if not p:
        return

    hoy = str(date.today())
    total_capital_pagado = session.query(func.sum(Pago.capital_pagado)).filter(Pago.prestamo_id == prestamo_id, Pago.fecha <= hoy).scalar() or 0

    capital_actual = max(0, (p.capital_inicial or 0) - total_capital_pagado)
    p.capital_actual = capital_actual
    session.commit()


def esta_prestamo_pagado(prestamo_id):
    deuda_interes, capital_real, _ = calcular_estado(prestamo_id)
    return capital_real == 0 and deuda_interes == 0

def calcular_estado(prestamo_id):
    p = session.get(Prestamo, prestamo_id)
    if not p:
        return 0, 0, 0

    capital_inicial = p.capital_inicial or 0
    tasa = p.tasa or 0
    fecha_inicio = p.fecha_inicio

    hoy = str(date.today())
    total_capital_pagado = session.query(func.sum(Pago.capital_pagado)).filter(Pago.prestamo_id == prestamo_id, Pago.fecha <= hoy).scalar() or 0

    capital_real = max(0, capital_inicial - total_capital_pagado)
    interes_mensual = capital_real * (tasa / 100)

    fecha_inicio_date = date.fromisoformat(fecha_inicio)

    meses_vencidos = meses_totales(str(fecha_inicio_date))
    interes_acumulado = 0
    for i in range(meses_vencidos):
        periodo = add_months(fecha_inicio_date, i + 1)
        capital_pagado_hasta_periodo = session.query(func.sum(Pago.capital_pagado)).filter(Pago.prestamo_id == prestamo_id, Pago.fecha <= str(periodo)).scalar() or 0
        capital_en_periodo = max(0, capital_inicial - capital_pagado_hasta_periodo)
        interes_acumulado += capital_en_periodo * (tasa / 100)

    interes_pagado = session.query(func.sum(Pago.interes_pagado)).filter(Pago.prestamo_id == prestamo_id).scalar() or 0

    deuda_interes = max(0, interes_acumulado - interes_pagado)

    return deuda_interes, capital_real, interes_mensual


def total_abonado_mes_general():
    mes_actual = date.today().strftime("%Y-%m")
    total = session.query(func.sum(Pago.monto)).filter(func.substr(Pago.fecha, 1, 7) == mes_actual).scalar() or 0
    return total


def aplicar_pago(prestamo_id, monto_capital, monto_interes, fecha_pago):
    monto_total = monto_capital + monto_interes
    pago = Pago(prestamo_id=prestamo_id, fecha=str(fecha_pago), monto=monto_total, interes_pagado=monto_interes, capital_pagado=monto_capital)
    session.add(pago)
    session.commit()

    recalcular_prestamo(prestamo_id)

    if esta_prestamo_pagado(prestamo_id):
        eliminar_prestamo(prestamo_id)
        return True

    return False

def eliminar_prestamo(prestamo_id):
    # Primero eliminar todos los pagos asociados y luego el préstamo
    p = session.get(Prestamo, prestamo_id)
    if not p:
        return
    session.delete(p)
    session.commit()

# ---------------- UI ----------------

st.set_page_config(page_title="Sistema de Préstamos", layout="wide")
st.title("💰 Sistema de Préstamos")

if "status_message" not in st.session_state:
    st.session_state.status_message = ""

if "menu" not in st.session_state:
    st.session_state.menu = "Resumen (tipo Excel)"

if "pago_repeat_pending" not in st.session_state:
    st.session_state.pago_repeat_pending = False

if "pago_status_message" not in st.session_state:
    st.session_state.pago_status_message = ""

if "pago_repeat_answer" not in st.session_state:
    st.session_state.pago_repeat_answer = "Sí"

if st.session_state.status_message:
    st.success(st.session_state.status_message)
    st.session_state.status_message = ""

# Menú lateral más compacto (radio) para mejor despliegue visual
display_menu = st.sidebar.radio("Menú", [
    "Resumen",
    "Nuevo préstamo",
    "Editar préstamo",
    "Registrar pago",
    "Editar pago",
    "Eliminar préstamo",
    "Ingresos mensuales",
    "Historial",
], index=0, key="menu_radio")

# Mapear opciones cortas a los valores usados en el código
menu_map = {
    "Resumen": "Resumen (tipo Excel)",
    "Nuevo préstamo": "Nuevo préstamo",
    "Editar préstamo": "Editar préstamo",
    "Registrar pago": "Registrar pago",
    "Editar pago": "Editar pago",
    "Eliminar préstamo": "Eliminar préstamo",
    "Ingresos mensuales": "Ingresos mensuales",
    "Historial": "Historial",
}

menu = menu_map.get(display_menu, "Resumen (tipo Excel)")

# ---------------- RESUMEN ----------------
if menu == "Resumen (tipo Excel)":
    st.header("📊 Resumen general")

    prestamos = session.query(Prestamo).all()

    # Calcular fecha próxima de pago para cada préstamo y ordenar por urgencia
    hoy = date.today()
    prestamos_con_fecha = []
    for p in prestamos:
        prox_vencimiento = prox_fecha_pago(p.fecha_inicio)
        prestamos_con_fecha.append((p, prox_vencimiento))

    # Ordenar por prioridad: hoy / vencido primero, luego más cercano
    prestamos_con_fecha.sort(
        key=lambda x: (
            0 if (x[1] - hoy).days <= 0 else 1,
            (x[1] - hoy).days,
            x[1]
        )
    )

    data = []
    total_interes_mensual = 0
    total_deudas = 0
    total_pagado_mes_general = total_abonado_mes_general()

    for p, prox_vencimiento in prestamos_con_fecha:
        deuda_interes, capital_real, interes_mensual = calcular_estado(p.id)
        total_interes_mensual += interes_mensual
        total_deuda_individual = capital_real + deuda_interes
        total_deudas += total_deuda_individual

        data.append({
            "Cliente": p.cliente,
            "Capital": round(capital_real, 2),
            "Interés mensual": round(interes_mensual, 2),
            "Interés pendiente": round(deuda_interes, 2),
            "Fecha inicio": p.fecha_inicio,
            "Próximo pago": prox_vencimiento.strftime("%Y-%m-%d"),
            "Total deuda": round(total_deuda_individual, 2)
        })

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total interés mensual ganado", f"${total_interes_mensual:,.2f}")
    with col2:
        st.metric("Total abonado este mes", f"${total_pagado_mes_general:,.2f}")
    with col3:
        st.metric("Total de todas las deudas", f"${total_deudas:,.2f}")

    st.dataframe(pd.DataFrame(data), width='stretch')

# ---------------- NUEVO ----------------
elif menu == "Nuevo préstamo":
    clientes_existentes = [r[0] for r in session.query(Prestamo.cliente).distinct().order_by(Prestamo.cliente).all()]

    cliente_seleccion = "Nuevo cliente"
    if clientes_existentes:
        cliente_seleccion = st.selectbox("Cliente", ["Nuevo cliente"] + clientes_existentes)

    if cliente_seleccion == "Nuevo cliente":
        cliente = st.text_input("Nombre del cliente")
    else:
        cliente = cliente_seleccion

    monto = st.number_input("Monto", min_value=0.0)
    tasa = st.number_input("Interés (%)", min_value=0.0)

    opcion_fecha = st.radio("Fecha", ["Hoy", "Elegir fecha"])
    fecha = date.today() if opcion_fecha == "Hoy" else st.date_input("Fecha")

    if st.button("Guardar"):
        if not cliente:
            st.error("Debes ingresar o seleccionar un cliente.")
        elif monto <= 0:
            st.error("El monto debe ser mayor a 0.")
        else:
            nuevo = Prestamo(cliente=cliente, capital_inicial=monto, capital_actual=monto, tasa=tasa, fecha_inicio=str(fecha))
            session.add(nuevo)
            session.commit()
            st.success("Préstamo creado")

# ---------------- EDITAR PRÉSTAMO ----------------
elif menu == "Editar préstamo":
    st.header("✏️ Editar préstamo")

    prestamos = session.query(Prestamo).all()

    if prestamos:
        opciones = {f"{p.cliente} (ID {p.id})": p for p in prestamos}
        seleccion = st.selectbox("Seleccionar préstamo", list(opciones.keys()))
        prestamo = opciones[seleccion]

        prestamo_id = prestamo.id
        deuda_interes, capital_real, interes_mensual = calcular_estado(prestamo_id)

        st.info(f"""
        **Estado actual:**
        - Capital actual: ${capital_real:,.2f}
        - Interés mensual: ${interes_mensual:,.2f}
        - Interés pendiente: ${deuda_interes:,.2f}
        """)

        st.divider()

        col1, col2 = st.columns(2)
        with col1:
            nuevo_cliente = st.text_input("Cliente", value=prestamo.cliente)
        with col2:
            nueva_tasa = st.number_input("Interés (%)", value=prestamo.tasa, min_value=0.0, step=0.01)

        col3, col4 = st.columns(2)
        with col3:
            nuevo_capital = st.number_input("Capital actual", value=prestamo.capital_actual, min_value=0.0, step=0.01)
        with col4:
            nueva_fecha = st.date_input("Fecha de inicio", value=date.fromisoformat(prestamo.fecha_inicio))

        if st.button("Actualizar préstamo"):
            prestamo.cliente = nuevo_cliente
            prestamo.tasa = nueva_tasa
            prestamo.capital_actual = nuevo_capital
            prestamo.fecha_inicio = str(nueva_fecha)
            session.commit()
            st.success("✅ Préstamo actualizado correctamente")
    else:
        st.warning("No hay préstamos para editar")

# ---------------- REGISTRAR PAGO ----------------
elif menu == "Registrar pago":
    prestamos = session.query(Prestamo).all()

    if prestamos:
        hoy = date.today()
        prestamos.sort(
            key=lambda p: (
                    0 if (prox_fecha_pago(p.fecha_inicio) - hoy).days <= 0 else 1,
                    (prox_fecha_pago(p.fecha_inicio) - hoy).days,
                    prox_fecha_pago(p.fecha_inicio)
            )
        )
        opciones = {f"{p.cliente} - Capital: ${p.capital_inicial} - Fecha: {p.fecha_inicio} (ID {p.id})": p.id for p in prestamos}
        seleccion = st.selectbox("Seleccionar deudor", list(opciones.keys()), key="pago_seleccion")
        prestamo_id = opciones[seleccion]

        if st.session_state.pago_repeat_pending:
            st.success(st.session_state.pago_status_message)
            st.write("¿Deseas realizar otro pago?")
            respuesta = st.radio("", ["Sí", "No"], key="pago_repeat_answer")
            if st.button("Continuar"):
                if respuesta == "Sí":
                    st.session_state.pago_monto_capital = 0.0
                    st.session_state.pago_monto_interes = 0.0
                    st.session_state.pago_opcion_fecha = "Hoy"
                    st.session_state.pago_fecha = date.today()
                    st.session_state.pago_repeat_pending = False
                    st.session_state.pago_status_message = ""
                    st.rerun()
                else:
                    st.session_state.pago_repeat_pending = False
                    st.session_state.pago_status_message = ""
                    st.session_state.menu_radio = "Resumen"
                    st.session_state.menu = "Resumen (tipo Excel)"
                    st.rerun()
            st.stop()

        deuda_interes, capital_real, interes_mensual = calcular_estado(prestamo_id)
        st.info(f"""
        **Estado actual del préstamo:**
        - Capital pendiente: ${capital_real:,.2f}
        - Interés mensual: ${interes_mensual:,.2f}
        - Interés pendiente: ${deuda_interes:,.2f}
        - **Total deuda estimada:** ${capital_real + deuda_interes:,.2f}
        """)

        st.divider()
        st.subheader("📝 Registrar abono")

        col1, col2 = st.columns(2)
        with col1:
            monto_capital = st.number_input("Monto a capital", min_value=0.0, step=0.01, key="pago_monto_capital")
        with col2:
            monto_interes = st.number_input("Monto a intereses", min_value=0.0, step=0.01, key="pago_monto_interes")

        opcion_fecha = st.radio("Fecha del abono", ["Hoy", "Elegir fecha"], key="pago_opcion_fecha")
        fecha_pago = date.today() if opcion_fecha == "Hoy" else st.date_input("Fecha", key="pago_fecha")

        if st.button("Aplicar abono"):
            monto_total = monto_capital + monto_interes
            if monto_total > 0:
                fully_paid = aplicar_pago(prestamo_id, monto_capital, monto_interes, fecha_pago)
                if fully_paid:
                    st.session_state.pago_status_message = "Pago registrado y el préstamo se eliminó porque quedó totalmente pagado."
                    st.balloons()
                else:
                    st.session_state.pago_status_message = "Pago registrado con éxito"
                st.session_state.pago_repeat_pending = True
                st.rerun()
            else:
                st.error("El monto total debe ser mayor a 0")
    else:
        st.warning("No hay deudores registrados")

# ---------------- EDITAR PAGO ----------------
elif menu == "Editar pago":
    st.header("✏️ Editar pago")

    pagos = session.query(Pago).join(Prestamo).order_by(Pago.fecha.desc()).all()

    if pagos:
        opciones = {f"Pago {p.id} | {p.prestamo.cliente} | {p.fecha} | Capital: ${p.capital_pagado:.2f} + Interés: ${p.interes_pagado:.2f}": p for p in pagos}

        seleccion = st.selectbox("Seleccionar pago", list(opciones.keys()))
        pago = opciones[seleccion]

        pago_id = pago.id
        prestamo_id = pago.prestamo_id
        interes_anterior = pago.interes_pagado
        capital_anterior = pago.capital_pagado

        fecha = st.date_input("Fecha", value=date.fromisoformat(pago.fecha))

        col1, col2 = st.columns(2)
        with col1:
            capital_pagado = st.number_input("Capital pagado", value=capital_anterior, min_value=0.0, step=0.01)
        with col2:
            interes_pagado = st.number_input("Interés pagado", value=interes_anterior, min_value=0.0, step=0.01)

        col3, col4 = st.columns([1, 1])
        with col3:
            if st.button("Actualizar pago"):
                monto_total = capital_pagado + interes_pagado
                pago.fecha = str(fecha)
                pago.monto = monto_total
                pago.interes_pagado = interes_pagado
                pago.capital_pagado = capital_pagado
                session.commit()
                recalcular_prestamo(prestamo_id)
                if esta_prestamo_pagado(prestamo_id):
                    eliminar_prestamo(prestamo_id)
                    st.session_state.status_message = "Pago modificado y el préstamo se eliminó porque quedó totalmente pagado."
                    st.balloons()
                else:
                    st.session_state.status_message = "Pago modificado con éxito"
                st.rerun()
        with col4:
            if st.button("Eliminar pago", type="secondary"):
                session.delete(pago)
                session.commit()
                recalcular_prestamo(prestamo_id)
                st.session_state.status_message = "Pago eliminado con éxito"
                st.rerun()
    else:
        st.info("No hay pagos registrados")

# ---------------- ELIMINAR PRÉSTAMO ----------------
elif menu == "Eliminar préstamo":
    st.header("🗑️ Eliminar préstamo")

    prestamos = session.query(Prestamo).all()

    if prestamos:
        opciones = {f"{p.cliente} (ID {p.id})": p for p in prestamos}
        seleccion = st.selectbox("Seleccionar préstamo a eliminar", list(opciones.keys()))
        prestamo = opciones[seleccion]

        prestamo_id = prestamo.id
        cliente = prestamo.cliente

        # Mostrar información del préstamo
        num_pagos = session.query(func.count(Pago.id)).filter(Pago.prestamo_id == prestamo_id).scalar()

        st.warning(f"⚠️ **Advertencia:** Esta acción eliminará permanentemente:")
        st.warning(f"- El préstamo de **{cliente}**")
        st.warning(f"- **{num_pagos}** pago(s) asociado(s)")

        st.error("Esta acción no se puede deshacer.")

        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("✅ Confirmar eliminación", type="primary"):
                eliminar_prestamo(prestamo_id)
                st.session_state.status_message = f"Préstamo de {cliente} y sus {num_pagos} pago(s) eliminados con éxito"
                st.rerun()
        with col2:
            st.button("❌ Cancelar", type="secondary")
    else:
        st.info("No hay préstamos para eliminar")

# ---------------- INGRESOS MENSUALES ----------------
elif menu == "Ingresos mensuales":
    st.header("📈 Ingresos mensuales")

    # Agrupar pagos por mes (YYYY-MM) y sumar monto
    rows = session.query(func.substr(Pago.fecha, 1, 7).label('mes'), func.sum(Pago.monto)).group_by('mes').order_by(func.substr(Pago.fecha, 1, 7).desc()).all()

    if rows:
        df_mensual = pd.DataFrame(rows, columns=["MesKey", "Total"])  # MesKey = 'YYYY-MM'
        df_mensual["Total"] = df_mensual["Total"].astype(float).round(2)

        # Formatear mes 'YYYY-MM' a formato legible en español, p.ej. 'junio 2026'
        meses_es = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre']
        def formato_legible(ym):
            if ym is None:
                return ""
            parts = str(ym).split('-')
            if len(parts) != 2:
                return ym
            y, m = parts[0], parts[1]
            try:
                m_idx = int(m) - 1
                return f"{meses_es[m_idx]} {y}"
            except Exception:
                return ym

        df_mensual["Mes"] = df_mensual["MesKey"].apply(formato_legible)

        st.subheader("Totales por mes")
        st.dataframe(df_mensual[["Mes", "Total"]], use_container_width=True)

        # Mostrar detalle por mes para verificar movimientos
        seleccion_mes = st.selectbox("Ver pagos del mes:", options=df_mensual["MesKey"].tolist(), format_func=lambda x: formato_legible(x))
        detalle = session.query(Pago.fecha, Prestamo.cliente, Pago.monto).join(Prestamo).filter(func.substr(Pago.fecha, 1, 7) == seleccion_mes).order_by(Pago.fecha).all()
        if detalle:
            df_detalle = pd.DataFrame(detalle, columns=["Fecha", "Cliente", "Monto"])            
            st.subheader(f"Detalle de pagos: {formato_legible(seleccion_mes)}")
            st.dataframe(df_detalle, use_container_width=True)
        else:
            st.info("No hay pagos en ese mes")
    else:
        st.info("No hay pagos registrados")

# ---------------- HISTORIAL ----------------
elif menu == "Historial":
    pagos = session.query(Prestamo.cliente, Pago.fecha, Pago.monto).join(Pago, Pago.prestamo_id == Prestamo.id).order_by(Pago.fecha.desc()).all()

    for p in pagos:
        st.write(f"{p[1]} | {p[0]} | ${p[2]}")
        st.divider()