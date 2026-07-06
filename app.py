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
    interes_cambios = relationship("InteresCambio", cascade="all, delete-orphan", backref="prestamo")


class Pago(Base):
    __tablename__ = "pagos"

    id = Column(Integer, primary_key=True)
    prestamo_id = Column(Integer, ForeignKey("prestamos.id"))
    fecha = Column(String)
    monto = Column(Float)
    interes_pagado = Column(Float)
    capital_pagado = Column(Float)


class InteresCambio(Base):
    __tablename__ = "interes_cambios"

    id = Column(Integer, primary_key=True)
    prestamo_id = Column(Integer, ForeignKey("prestamos.id"))
    tasa = Column(Float)
    fecha_desde = Column(String)


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


def meses_totales(fecha_inicio, fecha_corte=None):
    fecha_corte = fecha_corte or date.today()
    f = date.fromisoformat(fecha_inicio)
    meses = (fecha_corte.year - f.year) * 12 + (fecha_corte.month - f.month)
    if fecha_corte.day < f.day:
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


def obtener_tasa_para_periodo(periodo, tasa_original, tasa_nueva, fecha_vigencia):
    if isinstance(periodo, str):
        periodo = date.fromisoformat(periodo)

    if isinstance(fecha_vigencia, str):
        fecha_vigencia = date.fromisoformat(fecha_vigencia)

    if fecha_vigencia is None:
        return float(tasa_nueva if tasa_nueva is not None else (tasa_original or 0))

    if periodo >= fecha_vigencia:
        return float(tasa_nueva if tasa_nueva is not None else (tasa_original or 0))

    return float(tasa_original or 0)


def obtener_tasa_aplicable(session, prestamo_id, periodo):
    p = session.get(Prestamo, prestamo_id)
    if not p:
        return 0.0

    cambios = session.query(InteresCambio).filter(
        InteresCambio.prestamo_id == prestamo_id
    ).order_by(InteresCambio.fecha_desde).all()

    if not cambios:
        return float(p.tasa or 0)

    tasa_aplicable = None
    for cambio in cambios:
        fecha_desde = cambio.fecha_desde
        if not fecha_desde:
            continue
        fecha = date.fromisoformat(fecha_desde)
        if periodo >= fecha:
            tasa_aplicable = float(cambio.tasa or 0)
        else:
            break

    if tasa_aplicable is None:
        return float(p.tasa or 0)

    return tasa_aplicable


def asegurar_historial_tasas(session):
    prestamos = session.query(Prestamo).all()
    for p in prestamos:
        if not session.query(InteresCambio).filter(InteresCambio.prestamo_id == p.id).first():
            session.add(InteresCambio(
                prestamo_id=p.id,
                tasa=p.tasa or 0.0,
                fecha_desde=p.fecha_inicio or str(date.today())
            ))
    session.commit()


def inicializar_historial_tasas():
    try:
        session = get_session()
        asegurar_historial_tasas(session)
        session.close()
    except Exception as e:
        print("Error al asegurar historial de tasas:", e)


if not os.environ.get("PYTEST_CURRENT_TEST"):
    inicializar_historial_tasas()


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


def periodo_clave(fecha):
    if isinstance(fecha, str):
        fecha = date.fromisoformat(fecha)
    return fecha.strftime("%Y-%m")


def obtener_fecha_corte(session, prestamo_id):
    ultimo_pago_con_capital = (
        session.query(Pago.fecha)
        .filter(Pago.prestamo_id == prestamo_id, Pago.capital_pagado > 0)
        .order_by(Pago.fecha.desc())
        .first()
    )
    if ultimo_pago_con_capital and ultimo_pago_con_capital[0]:
        return date.fromisoformat(ultimo_pago_con_capital[0])

    return None


def aplicar_pagos_a_intereses(periodos, pagos):
    saldos = [float(due) for _, due in periodos]

    for fecha_pago, monto in sorted(pagos, key=lambda item: item[0]):
        if monto <= 0:
            continue

        restante_pago = float(monto)
        for idx, (periodo, _) in enumerate(periodos):
            if periodo > fecha_pago:
                continue
            if restante_pago <= 0:
                break
            if saldos[idx] <= 0:
                continue

            if saldos[idx] >= restante_pago:
                saldos[idx] -= restante_pago
                restante_pago = 0
            else:
                restante_pago -= saldos[idx]
                saldos[idx] = 0

    return saldos


def capital_pagado_hasta_periodo(pagos_capital, periodo):
    if not pagos_capital:
        return 0.0

    periodo_key = periodo_clave(periodo)
    total = 0.0
    for pago in pagos_capital:
        if periodo_clave(pago.fecha) <= periodo_key:
            total += float(pago.capital_pagado or 0)
    return total


def calcular_estado(session, prestamo_id):
    p = session.get(Prestamo, prestamo_id)
    if not p:
        return 0, 0, 0

    capital_inicial = p.capital_inicial or 0
    fecha_inicio = date.fromisoformat(p.fecha_inicio)

    total_capital_pagado = session.query(
        func.sum(Pago.capital_pagado)
    ).filter(
        Pago.prestamo_id == prestamo_id
    ).scalar() or 0

    capital_real = max(0, capital_inicial - total_capital_pagado)
    interes_mensual = capital_real * (obtener_tasa_aplicable(session, prestamo_id, date.today()) / 100)

    fecha_corte = obtener_fecha_corte(session, prestamo_id)
    meses_vencidos = meses_totales(str(fecha_inicio), fecha_corte or date.today())

    if fecha_corte and fecha_corte < date.today():
        if prox_fecha_pago(str(fecha_inicio)) <= date.today():
            meses_vencidos = max(meses_vencidos, meses_totales(str(fecha_inicio), date.today()))
    periodos = []
    pagos_capital = session.query(Pago).filter(
        Pago.prestamo_id == prestamo_id,
        Pago.capital_pagado > 0
    ).order_by(Pago.fecha).all()

    capital_acumulado = 0.0
    for i in range(meses_vencidos):
        periodo = add_months(fecha_inicio, i + 1)

        capital_acumulado += capital_pagado_hasta_periodo(pagos_capital, periodo) - capital_acumulado
        capital_periodo = max(0, capital_inicial - capital_acumulado)
        tasa_periodo = obtener_tasa_aplicable(session, prestamo_id, periodo)
        interes_periodo = capital_periodo * (tasa_periodo / 100)
        periodos.append((periodo, interes_periodo))

    pagos_interes = session.query(Pago).filter(
        Pago.prestamo_id == prestamo_id,
        Pago.interes_pagado > 0
    ).order_by(Pago.fecha).all()

    pagos = []
    for pago in pagos_interes:
        pagos.append((date.fromisoformat(pago.fecha), float(pago.interes_pagado or 0)))

    saldos = aplicar_pagos_a_intereses(periodos, pagos)
    deuda_interes = sum(max(0, saldo) for saldo in saldos)

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


def ir_a_menu(nuevo_menu):
    st.session_state["menu"] = nuevo_menu
    st.rerun()


if "menu" not in st.session_state:
    st.session_state["menu"] = "Resumen"

menu = st.sidebar.radio("Menú", [
    "Resumen",
    "Nuevo préstamo",
    "Registrar pago",
    "Historial mensual",
    "Editar préstamo",
    "Editar pago",
    "Eliminar préstamo",
], key="menu")

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
        session.add(InteresCambio(
            prestamo_id=p.id,
            tasa=tasa,
            fecha_desde=p.fecha_inicio,
        ))
        session.commit()
        st.success("Préstamo creado")


# =================================================
# REGISTRAR PAGO
# =================================================

elif menu == "Registrar pago":
    prestamos = session.query(Prestamo).all()
    # Construir opciones mostrando estado: cliente, capital actual e interés pendiente
    opciones = {}
    estado_map = {}
    for p in prestamos:
        deuda_interes, capital_real, interes_mensual = calcular_estado(session, p.id)
        label = f"{p.cliente} | Capital: ${capital_real:.2f} | Interés pendiente: ${deuda_interes:.2f} (ID {p.id})"
        opciones[label] = p.id
        estado_map[p.id] = {
            "deuda_interes": float(round(deuda_interes, 2)),
            "capital_real": float(round(capital_real, 2)),
            "interes_mensual": float(round(interes_mensual, 2))
        }

    if opciones:
        sel = st.selectbox("Préstamo", list(opciones.keys()))
        pid = opciones[sel]

        estado = estado_map.get(pid, {})

        st.info(f"Cliente: {sel.split('|')[0].strip()}")
        st.write(f"- Capital actual: ${estado.get('capital_real', 0):,.2f}")
        st.write(f"- Interés pendiente: ${estado.get('deuda_interes', 0):,.2f}")
        st.write(f"- Interés mensual estimado: ${estado.get('interes_mensual', 0):,.2f}")
        st.divider()

        # Campos para registrar pago (sugerir interés pendiente en el campo)
        cap = st.number_input("Capital", min_value=0.0, value=0.0)
        intp = st.number_input("Interés", min_value=0.0, value=float(estado.get('deuda_interes', 0.0)))
        fecha = st.date_input("Fecha")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Aplicar pago"):
                eliminado = aplicar_pago(session, pid, cap, intp, fecha)
                if eliminado:
                    st.success("Préstamo eliminado")
                else:
                    st.success("Pago registrado")

                st.divider()
                st.write("¿Desea realizar otro pago?")
                c_yes, c_no = st.columns(2)
                if c_yes.button("Sí, realizar otro pago"):
                    st.rerun()
                if c_no.button("No, mostrar resumen"):
                    ir_a_menu("Resumen")
        with col2:
            if st.button("Pagar total (efectuar pago completo)", type="secondary"):
                cap_total = estado.get('capital_real', 0.0)
                int_total = estado.get('deuda_interes', 0.0)
                eliminado = aplicar_pago(session, pid, cap_total, int_total, fecha)
                if eliminado:
                    st.success("Préstamo eliminado")
                else:
                    st.success("Pago total registrado")

                st.divider()
                st.write("¿Desea realizar otro pago?")
                c_yes2, c_no2 = st.columns(2)
                if c_yes2.button("Sí, realizar otro pago"):
                    st.rerun()
                if c_no2.button("No, mostrar resumen"):
                    ir_a_menu("Resumen")


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
            st.info(f"Fecha de inicio actual: {prestamo.fecha_inicio}")
            st.caption("La fecha de inicio del préstamo se conserva; el nuevo interés solo empieza a regir desde la fecha que elijas abajo.")
            fecha_vigencia_tasa = st.date_input(
                "Desde qué fecha rige este interés",
                value=date.today(),
                help="Los meses anteriores a esta fecha seguirán usando el interés anterior y solo los meses pendientes se recalcularán con el nuevo interés."
            )

        if st.button("Guardar cambios"):
            prestamo.cliente = nuevo_cliente
            prestamo.capital_actual = nuevo_capital
            tasa_anterior = prestamo.tasa or 0.0
            prestamo.tasa = nueva_tasa

            if nueva_tasa != tasa_anterior:
                session.add(InteresCambio(
                    prestamo_id=prestamo.id,
                    tasa=nueva_tasa,
                    fecha_desde=str(fecha_vigencia_tasa),
                ))

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