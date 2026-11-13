"""Pruebas del generador de datos (servicio `app`)."""

from __future__ import annotations

import pytest

from simulador import config_por_defecto, generar


def test_el_catalogo_tiene_las_siete_piezas():
    config = config_por_defecto()
    assert len(config.componentes) == 7
    assert len(config.cotas) == 82
    assert {c.codigo for c in config.componentes} == {
        "BAS", "BR1", "CIL", "CCH", "EST", "PLM", "TNS"
    }


def test_una_corrida_genera_siete_piezas_y_ochenta_y_dos_mediciones():
    config = config_por_defecto()
    resultado = generar(config, conjuntos=3, semilla=1)

    assert len(resultado.conjuntos) == 3
    assert len(resultado.piezas) == 3 * 7
    assert len(resultado.mediciones) == 3 * 82


def test_el_resultado_es_reproducible_con_la_misma_semilla():
    config = config_por_defecto()
    uno = generar(config, conjuntos=5, semilla=7)
    dos = generar(config, conjuntos=5, semilla=7)
    assert uno.resumen["tasa_nok"] == dos.resumen["tasa_nok"]
    assert [p["estado"] for p in uno.piezas] == [p["estado"] for p in dos.piezas]


def test_cada_medicion_esta_evaluada_contra_su_tolerancia():
    config = config_por_defecto()
    resultado = generar(config, conjuntos=4, semilla=3, escala_defectos=4.0)
    catalogo = {c.codigo: c for c in config.cotas}

    for medicion in resultado.mediciones:
        cota = catalogo[medicion["codigo_cota"]]
        dentro = cota.limite_inferior <= medicion["valor"] <= cota.limite_superior
        assert medicion["ok"] == int(dentro)


def test_la_sigma_se_deriva_del_cpk_objetivo():
    config = config_por_defecto()
    cota = next(c for c in config.cotas if c.codigo == "BR1-C01")
    objetivo = cota.banda / (6 * cota.cpk_objetivo)
    efectiva = (
        cota.sigma_proceso**2 * (1 + cota.carga_comun**2) + cota.sigma_medicion**2
    ) ** 0.5
    assert efectiva == pytest.approx(objetivo, rel=0.02)


def test_la_deriva_aumenta_la_dispersion_al_final_de_la_herramienta():
    config = config_por_defecto()
    config.proceso.vida_herramienta = 10
    config.defectos.deriva_total_sigmas = 3.0  # deriva marcada, para verla pese al ruido
    resultado = generar(config, conjuntos=200, semilla=5)

    cota = next(c for c in config.cotas if c.codigo == "BR1-C01")
    pares = [
        (abs(m["valor"] - cota.nominal), p["piezas_en_herramienta"])
        for m, p in zip(
            [m for m in resultado.mediciones if m["codigo_cota"] == "BR1-C01"],
            [p for p in resultado.piezas if p["codigo_pieza"] == "BR1"],
        )
    ]
    inicio = [d for d, pos in pares if pos < 2]
    final = [d for d, pos in pares if pos >= 8]

    assert sum(final) / len(final) > sum(inicio) / len(inicio)
