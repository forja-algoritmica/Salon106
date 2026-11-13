"""Catálogo semilla del ensamble del brazo de retroexcavadora.

Cada tupla es una característica dimensional de un componente:
    (id_pieza, codigo_pieza, nombre_pieza, codigo_cota, nombre_cota,
     tipo, nominal, tol_inf, tol_sup)

Estos datos se escriben una sola vez en `config/catalogo_cotas.csv`, que pasa a
ser el archivo maestro: a partir de ahí se edita en Excel y no en el código.
"""

from __future__ import annotations

# Tipos admitidos: Lineal, Espesor, Diámetro, Radio, Ángulo.
SEED: list[tuple] = [
    # ------------------------------------------------------------------
    # 1. BASE
    # ------------------------------------------------------------------
    (1, "BAS", "Base", "BAS-C01", "Ancho total exterior", "Lineal", 710.00, -0.500, 0.500),
    (1, "BAS", "Base", "BAS-C02", "Altura total exterior", "Lineal", 765.00, -0.500, 0.500),
    (1, "BAS", "Base", "BAS-C03", "Profundidad a centro de barreno inferior", "Lineal", 595.00, -0.500, 0.500),
    (1, "BAS", "Base", "BAS-C04", "Distancia posterior a centro barreno base", "Lineal", 495.00, -0.500, 0.500),
    (1, "BAS", "Base", "BAS-C05", "Extensión de orejas traseras", "Lineal", 285.00, -0.500, 0.500),
    (1, "BAS", "Base", "BAS-C06", "Abertura interior del marco principal", "Lineal", 506.00, -0.500, 0.500),
    (1, "BAS", "Base", "BAS-C07", "Espaciado entre orejas superiores", "Lineal", 200.00, -0.300, 0.300),
    (1, "BAS", "Base", "BAS-C08", "Espesor de placas principales", "Espesor", 102.00, -0.200, 0.200),
    (1, "BAS", "Base", "BAS-C09", "Espesor de orejas superiores", "Espesor", 75.00, -0.200, 0.200),
    (1, "BAS", "Base", "BAS-C10", "Diámetro barreno posterior base", "Diámetro", 150.00, -0.050, 0.050),
    (1, "BAS", "Base", "BAS-C11", "Diámetro barreno inferior principal", "Diámetro", 102.00, -0.050, 0.050),
    (1, "BAS", "Base", "BAS-C12", "Diámetro barrenos orejas superiores", "Diámetro", 76.00, -0.040, 0.040),
    (1, "BAS", "Base", "BAS-C13", "Radio exterior base posterior", "Radio", 205.00, -0.500, 0.500),
    (1, "BAS", "Base", "BAS-C14", "Radio inferior de orejas", "Radio", 150.00, -0.500, 0.500),
    (1, "BAS", "Base", "BAS-C15", "Radio superior de orejas", "Radio", 90.00, -0.500, 0.500),
    (1, "BAS", "Base", "BAS-C16", "Ángulo de inclinación de orejas", "Ángulo", 50.00, -0.500, 0.500),
    # ------------------------------------------------------------------
    # 2. BRAZO 1
    # ------------------------------------------------------------------
    (2, "BR1", "Brazo 1", "BR1-C01", "Longitud total de estructura", "Lineal", 3250.00, -1.000, 1.000),
    (2, "BR1", "Brazo 1", "BR1-C02", "Distancia entre centros principales", "Lineal", 3050.00, -0.800, 0.800),
    (2, "BR1", "Brazo 1", "BR1-C03", "Extensión trasera desde centro", "Lineal", 610.00, -0.500, 0.500),
    (2, "BR1", "Brazo 1", "BR1-C04", "Longitud de perfil superior recto", "Lineal", 1970.00, -0.800, 0.800),
    (2, "BR1", "Brazo 1", "BR1-C05", "Longitud de placa de refuerzo inferior", "Lineal", 1410.00, -0.800, 0.800),
    (2, "BR1", "Brazo 1", "BR1-C06", "Ancho exterior total", "Lineal", 306.00, -0.500, 0.500),
    (2, "BR1", "Brazo 1", "BR1-C07", "Ancho interior libre", "Lineal", 200.00, -0.400, 0.400),
    (2, "BR1", "Brazo 1", "BR1-C08", "Desfase vertical de barrenos traseros", "Lineal", 305.00, -0.500, 0.500),
    (2, "BR1", "Brazo 1", "BR1-C09", "Desfase vertical de barrenos frontales", "Lineal", 127.00, -0.500, 0.500),
    (2, "BR1", "Brazo 1", "BR1-C10", "Espesor de placas laterales", "Espesor", 53.00, -0.200, 0.200),
    (2, "BR1", "Brazo 1", "BR1-C11", "Diámetro barreno central principal", "Diámetro", 102.00, -0.050, 0.050),
    (2, "BR1", "Brazo 1", "BR1-C12", "Diámetro barrenos de articulación", "Diámetro", 76.00, -0.040, 0.040),
    (2, "BR1", "Brazo 1", "BR1-C13", "Radio exterior frontal", "Radio", 127.00, -0.500, 0.500),
    (2, "BR1", "Brazo 1", "BR1-C14", "Radio exterior superior trasero", "Radio", 205.00, -0.500, 0.500),
    # ------------------------------------------------------------------
    # 3. CILINDRO
    # ------------------------------------------------------------------
    (3, "CIL", "Cilindro", "CIL-C01", "Longitud extendida centro a centro", "Lineal", 2675.00, -1.000, 1.000),
    (3, "CIL", "Cilindro", "CIL-C02", "Longitud total de camisa", "Lineal", 1800.00, -0.800, 0.800),
    (3, "CIL", "Cilindro", "CIL-C03", "Longitud interna útil de camisa", "Lineal", 1825.00, -0.800, 0.800),
    (3, "CIL", "Cilindro", "CIL-C04", "Longitud de casquillo terminal", "Lineal", 165.00, -0.300, 0.300),
    (3, "CIL", "Cilindro", "CIL-C05", "Diámetro exterior de la camisa", "Diámetro", 180.00, -0.200, 0.200),
    (3, "CIL", "Cilindro", "CIL-C06", "Diámetro interior del cilindro", "Diámetro", 150.00, -0.050, 0.050),
    (3, "CIL", "Cilindro", "CIL-C07", "Diámetro exterior del vástago", "Diámetro", 102.00, -0.030, 0.030),
    (3, "CIL", "Cilindro", "CIL-C08", "Diámetro exterior de ojo terminal", "Diámetro", 179.80, -0.100, 0.100),
    (3, "CIL", "Cilindro", "CIL-C09", "Diámetro interior de barrenos (ojos)", "Diámetro", 76.00, -0.030, 0.030),
    (3, "CIL", "Cilindro", "CIL-C10", "Ancho exterior ojo vástago", "Espesor", 199.78, -0.200, 0.200),
    # ------------------------------------------------------------------
    # 4. CUCHARA
    # ------------------------------------------------------------------
    (4, "CCH", "Cuchara", "CCH-C01", "Longitud / Profundidad total", "Lineal", 780.00, -0.800, 0.800),
    (4, "CCH", "Cuchara", "CCH-C02", "Ancho exterior total", "Lineal", 306.00, -0.500, 0.500),
    (4, "CCH", "Cuchara", "CCH-C03", "Separación entre orejas de acople", "Lineal", 300.00, -0.400, 0.400),
    (4, "CCH", "Cuchara", "CCH-C04", "Distancia de fijación frontal", "Lineal", 385.00, -0.500, 0.500),
    (4, "CCH", "Cuchara", "CCH-C05", "Espesor de placa de labio / reforzada", "Espesor", 50.00, -0.200, 0.200),
    (4, "CCH", "Cuchara", "CCH-C06", "Espesor de placas laterales", "Espesor", 40.00, -0.200, 0.200),
    (4, "CCH", "Cuchara", "CCH-C07", "Espesor de refuerzos secundarios", "Espesor", 25.00, -0.200, 0.200),
    (4, "CCH", "Cuchara", "CCH-C08", "Espesor de lámina de cuerpo", "Espesor", 12.00, -0.200, 0.200),
    (4, "CCH", "Cuchara", "CCH-C09", "Diámetro barrenos de acople", "Diámetro", 76.00, -0.040, 0.040),
    (4, "CCH", "Cuchara", "CCH-C10", "Ángulo de corte principal", "Ángulo", 160.00, -0.500, 0.500),
    (4, "CCH", "Cuchara", "CCH-C11", "Ángulo de inclinación de base", "Ángulo", 120.00, -0.500, 0.500),
    (4, "CCH", "Cuchara", "CCH-C12", "Ángulo de ataque frontal", "Ángulo", 60.00, -0.500, 0.500),
    # ------------------------------------------------------------------
    # 5. ESTABILIZADOR
    # ------------------------------------------------------------------
    (5, "EST", "Estabilizador", "EST-C01", "Distancia entre centros de barrenos", "Lineal", 460.00, -0.500, 0.500),
    (5, "EST", "Estabilizador", "EST-C02", "Ancho exterior total", "Lineal", 306.00, -0.500, 0.500),
    (5, "EST", "Estabilizador", "EST-C03", "Ancho exterior de cuerpo central", "Lineal", 212.00, -0.400, 0.400),
    (5, "EST", "Estabilizador", "EST-C04", "Ventana interior libre", "Lineal", 200.00, -0.400, 0.400),
    (5, "EST", "Estabilizador", "EST-C05", "Espesor de orejas exteriores", "Espesor", 53.00, -0.200, 0.200),
    (5, "EST", "Estabilizador", "EST-C06", "Espesor de placas interiores", "Espesor", 41.00, -0.200, 0.200),
    (5, "EST", "Estabilizador", "EST-C07", "Diámetro barreno grande", "Diámetro", 150.00, -0.050, 0.050),
    (5, "EST", "Estabilizador", "EST-C08", "Diámetro barreno pequeño", "Diámetro", 76.00, -0.040, 0.040),
    # ------------------------------------------------------------------
    # 6. PLUMA
    # ------------------------------------------------------------------
    (6, "PLM", "Pluma", "PLM-C01", "Longitud total de punta a punta", "Lineal", 4525.00, -1.200, 1.200),
    (6, "PLM", "Pluma", "PLM-C02", "Distancia entre centros principales", "Lineal", 2795.00, -0.800, 0.800),
    (6, "PLM", "Pluma", "PLM-C03", "Distancia frontal a torre central", "Lineal", 2050.00, -0.800, 0.800),
    (6, "PLM", "Pluma", "PLM-C04", "Distancia posterior a centro barreno", "Lineal", 706.00, -0.500, 0.500),
    (6, "PLM", "Pluma", "PLM-C05", "Altura superior desde eje central", "Lineal", 570.00, -0.500, 0.500),
    (6, "PLM", "Pluma", "PLM-C06", "Altura inferior desde eje central", "Lineal", 400.00, -0.500, 0.500),
    (6, "PLM", "Pluma", "PLM-C07", "Ancho exterior total", "Lineal", 506.00, -0.500, 0.500),
    (6, "PLM", "Pluma", "PLM-C08", "Ancho interior libre de caja", "Lineal", 306.00, -0.400, 0.400),
    (6, "PLM", "Pluma", "PLM-C09", "Espesor de placas estructurales", "Espesor", 100.00, -0.200, 0.200),
    (6, "PLM", "Pluma", "PLM-C10", "Espesor de soporte de oreja", "Espesor", 53.00, -0.200, 0.200),
    (6, "PLM", "Pluma", "PLM-C11", "Diámetro barrenos de articulación", "Diámetro", 102.00, -0.050, 0.050),
    (6, "PLM", "Pluma", "PLM-C12", "Diámetro barreno central grande", "Diámetro", 180.00, -0.060, 0.060),
    (6, "PLM", "Pluma", "PLM-C13", "Diámetro barreno de cilindro", "Diámetro", 76.00, -0.040, 0.040),
    (6, "PLM", "Pluma", "PLM-C14", "Ángulo de inclinación superior", "Ángulo", 45.00, -0.500, 0.500),
    (6, "PLM", "Pluma", "PLM-C15", "Ángulo de perfil cuerpo frontal", "Ángulo", 26.00, -0.500, 0.500),
    (6, "PLM", "Pluma", "PLM-C16", "Ángulo de caída posterior", "Ángulo", 5.00, -0.200, 0.200),
    # ------------------------------------------------------------------
    # 7. TENSOR
    # ------------------------------------------------------------------
    (7, "TNS", "Tensor", "TNS-C01", "Distancia entre centros de barrenos", "Lineal", 610.00, -0.500, 0.500),
    (7, "TNS", "Tensor", "TNS-C02", "Espesor del cuerpo principal", "Espesor", 50.00, -0.200, 0.200),
    (7, "TNS", "Tensor", "TNS-C03", "Diámetro barreno grande", "Diámetro", 150.00, -0.050, 0.050),
    (7, "TNS", "Tensor", "TNS-C04", "Diámetro barreno pequeño", "Diámetro", 76.00, -0.040, 0.040),
    (7, "TNS", "Tensor", "TNS-C05", "Radio de curvatura mayor", "Radio", 460.00, -0.500, 0.500),
    (7, "TNS", "Tensor", "TNS-C06", "Radio de curvatura menor", "Radio", 305.00, -0.500, 0.500),
]
