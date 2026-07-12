import unittest
from datetime import date
from unittest.mock import patch

import app


class TasaPorPeriodoTests(unittest.TestCase):
    def test_usa_tasa_original_antes_de_la_fecha_de_vigencia(self):
        tasa_original = 10.0
        tasa_nueva = 15.0
        fecha_vigencia = date(2024, 3, 1)

        self.assertEqual(
            app.obtener_tasa_para_periodo(date(2024, 2, 1), tasa_original, tasa_nueva, fecha_vigencia),
            10.0,
        )

    def test_usa_tasa_nueva_desde_la_fecha_de_vigencia(self):
        tasa_original = 10.0
        tasa_nueva = 15.0
        fecha_vigencia = date(2024, 3, 1)

        self.assertEqual(
            app.obtener_tasa_para_periodo(date(2024, 3, 15), tasa_original, tasa_nueva, fecha_vigencia),
            15.0,
        )

    def test_aplica_pago_de_interes_al_periodo_correspondiente(self):
        periodos = [(date(2026, 6, 1), 75.0)]
        pagos = [(date(2026, 6, 15), 75.0)]

        self.assertEqual(app.aplicar_pagos_a_intereses(periodos, pagos), [0.0])

    def test_pago_antes_del_vencimiento_si_se_aplica(self):
        """Un pago de interés antes de la fecha de vencimiento sí debe aplicarse
        al periodo correspondiente (pago adelantado)."""
        periodos = [(date(2026, 5, 26), 100.0)]
        pagos = [(date(2026, 5, 6), 100.0)]

        self.assertEqual(app.aplicar_pagos_a_intereses(periodos, pagos), [0.0])

    def test_meses_totales_usa_la_fecha_de_corte(self):
        self.assertEqual(app.meses_totales("2026-05-01", date(2026, 6, 15)), 1)
        self.assertEqual(app.meses_totales("2026-05-01", date(2026, 7, 5)), 2)

    def test_un_pago_no_borra_periodos_futuros(self):
        periodos = [(date(2026, 4, 1), 100.0), (date(2026, 5, 1), 100.0)]
        pagos = [(date(2026, 4, 13), 100.0)]

        self.assertEqual(app.aplicar_pagos_a_intereses(periodos, pagos), [0.0, 100.0])

    def test_corta_el_calculo_al_ultimo_abono_a_capital(self):
        session = app.get_session()
        try:
            prestamo = app.Prestamo(
                cliente="Test2",
                capital_inicial=100.0,
                capital_actual=100.0,
                tasa=10.0,
                fecha_inicio="2026-05-01",
            )
            session.add(prestamo)
            session.commit()
            session.add(
                app.Pago(
                    prestamo_id=prestamo.id,
                    fecha="2026-06-30",
                    monto=160.0,
                    interes_pagado=60.0,
                    capital_pagado=100.0,
                )
            )
            session.commit()
            self.assertEqual(app.obtener_fecha_corte(session, prestamo.id), date(2026, 6, 30))
        finally:
            session.close()

    def test_david_fuentes_muestra_interes_pendiente_del_mes_actual(self):
        session = app.get_session()
        try:
            class FrozenDate(date):
                @classmethod
                def today(cls):
                    return cls(2026, 7, 5)

            prestamo = app.Prestamo(
                cliente="David Fuentes",
                capital_inicial=280.0,
                capital_actual=280.0,
                tasa=20.0,
                fecha_inicio="2026-04-05",
            )
            session.add(prestamo)
            session.commit()

            session.add(
                app.Pago(
                    prestamo_id=prestamo.id,
                    fecha="2026-05-14",
                    monto=100.0,
                    interes_pagado=56.0,
                    capital_pagado=44.0,
                )
            )
            session.add(
                app.Pago(
                    prestamo_id=prestamo.id,
                    fecha="2026-06-11",
                    monto=80.0,
                    interes_pagado=47.2,
                    capital_pagado=32.8,
                )
            )
            session.commit()

            with patch.object(app, "date", FrozenDate):
                deuda_interes, _, _ = app.calcular_estado(session, prestamo.id)

            self.assertAlmostEqual(deuda_interes, 40.64)
        finally:
            session.close()

    def test_un_pago_con_abono_a_capital_deja_interes_del_mes_siguiente(self):
        """Si hay un pago en junio y hoy es julio, debe haber interés pendiente de junio."""
        session = app.get_session()
        try:
            class FrozenDate(date):
                @classmethod
                def today(cls):
                    return cls(2026, 7, 5)

            prestamo = app.Prestamo(
                cliente="Maricela",
                capital_inicial=500.0,
                capital_actual=500.0,
                tasa=15.0,
                fecha_inicio="2026-05-01",
            )
            session.add(prestamo)
            session.commit()

            session.add(
                app.Pago(
                    prestamo_id=prestamo.id,
                    fecha="2026-06-15",
                    monto=175.0,
                    interes_pagado=75.0,
                    capital_pagado=100.0,
                )
            )
            session.commit()

            with patch.object(app, "date", FrozenDate):
                deuda_interes, _, _ = app.calcular_estado(session, prestamo.id)

            # Periodo 1 (mayo): capital $500, interés $75 -> pagado
            # Periodo 2 (junio): capital $400, interés $60 -> NO pagado
            self.assertAlmostEqual(deuda_interes, 60.0)
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
