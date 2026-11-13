"""Configuración del ensamble: catálogo de cotas + parámetros del proceso.

El catálogo (qué piezas, qué cotas, nominales y tolerancias) vive en
`config/catalogo_cotas.csv` para poder editarlo en Excel. El resto de
parámetros (velocidad de línea, causas de defecto, salida) vive en
`config/proceso.json`.

De la tolerancia de cada cota se derivan automáticamente su variación de
proceso y su error de medición, de modo que no hay que calibrar 82 números a
mano: se pide un Cpk objetivo y el simulador calcula la sigma.
"""

from __future__ import annotations

import csv
import json
import unicodedata
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, get_args, get_origin, get_type_hints

from .catalogo import SEED

# Coeficiente de dilatación lineal del acero [1/°C].
CTE_ACERO = 11.5e-6

# Valores por defecto según el tipo de característica.
PERFILES: dict[str, dict[str, Any]] = {
    "lineal": {"unidad": "mm", "decimales": 3, "cpk": 1.33, "carga_comun": 0.35, "deriva": 0.7},
    "espesor": {"unidad": "mm", "decimales": 3, "cpk": 1.33, "carga_comun": 0.35, "deriva": 0.6},
    "diametro": {"unidad": "mm", "decimales": 3, "cpk": 1.67, "carga_comun": 0.45, "deriva": 1.0},
    "radio": {"unidad": "mm", "decimales": 3, "cpk": 1.33, "carga_comun": 0.30, "deriva": 0.5},
    "angulo": {"unidad": "°", "decimales": 2, "cpk": 1.33, "carga_comun": 0.40, "deriva": 0.6},
}

COLUMNAS_CATALOGO = [
    "id_pieza",
    "codigo_pieza",
    "nombre_pieza",
    "codigo_cota",
    "nombre_cota",
    "tipo",
    "nominal",
    "tol_inf",
    "tol_sup",
    "unidad",
    "cpk_objetivo",
    "decimales",
]


def normalizar_tipo(tipo: str) -> str:
    """'Diámetro' -> 'diametro', 'Ángulo' -> 'angulo'."""
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", tipo) if unicodedata.category(c) != "Mn"
    )
    return sin_acentos.strip().lower().replace(" ", "_")


def _numero(texto: Any) -> float:
    """Acepta '1,5' y '1.5' (Excel en español escribe con coma)."""
    if isinstance(texto, (int, float)):
        return float(texto)
    limpio = str(texto).strip().replace(" ", "")
    if "," in limpio and "." not in limpio:
        limpio = limpio.replace(",", ".")
    return float(limpio)


# ---------------------------------------------------------------------------
# Cota
# ---------------------------------------------------------------------------
@dataclass
class Cota:
    """Una característica dimensional de un componente."""

    codigo: str
    nombre: str
    tipo: str
    nominal: float
    tol_inf: float
    tol_sup: float
    unidad: str = "mm"
    decimales: int = 3
    cpk_objetivo: float = 1.33
    sigma_proceso: float = 0.0
    sigma_medicion: float = 0.0
    carga_comun: float = 0.35
    factor_deriva: float = 0.7
    signo_deriva: float = 1.0
    sesgo: float = 0.0
    sensibilidad: dict[str, float] = field(default_factory=dict)
    solo_positivo: bool = False

    def __post_init__(self) -> None:
        self.tipo = normalizar_tipo(self.tipo)
        if self.tipo not in PERFILES:
            raise ValueError(
                f"{self.codigo}: tipo {self.tipo!r} no válido. "
                f"Use uno de: {', '.join(PERFILES)}"
            )
        if self.tol_inf > 0 or self.tol_sup < 0:
            raise ValueError(f"{self.codigo}: 'tol_inf' <= 0 y 'tol_sup' >= 0")
        if self.tol_inf >= self.tol_sup:
            raise ValueError(f"{self.codigo}: 'tol_inf' debe ser menor que 'tol_sup'")
        if self.cpk_objetivo <= 0:
            raise ValueError(f"{self.codigo}: 'cpk_objetivo' debe ser > 0")

        # Error del instrumento: ~1/18 de la banda de tolerancia.
        if self.sigma_medicion <= 0:
            self.sigma_medicion = self.banda / 18.0

        # Variación del proceso: se descuenta del Cpk objetivo la parte que ya
        # aportan el instrumento y la causa común, para que la capacidad
        # alcanzada se parezca a la pedida.
        if self.sigma_proceso <= 0:
            objetivo = self.banda / (6.0 * self.cpk_objetivo)
            varianza = objetivo**2 - self.sigma_medicion**2
            varianza = max(varianza, (0.5 * objetivo) ** 2)
            self.sigma_proceso = (varianza / (1.0 + self.carga_comun**2)) ** 0.5

        # Dilatación térmica proporcional al tamaño nominal.
        if not self.sensibilidad:
            self.sensibilidad = {"temperatura": CTE_ACERO * abs(self.nominal)}

    @property
    def limite_inferior(self) -> float:
        return self.nominal + self.tol_inf

    @property
    def limite_superior(self) -> float:
        return self.nominal + self.tol_sup

    @property
    def banda(self) -> float:
        return self.tol_sup - self.tol_inf


@dataclass
class Componente:
    id: int
    codigo: str
    nombre: str
    cotas: list[Cota] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.codigo.strip():
            raise ValueError("El componente necesita un código")


# ---------------------------------------------------------------------------
# Proceso
# ---------------------------------------------------------------------------
@dataclass
class Proceso:
    conjuntos: int = 500  # ensambles completos a generar
    semilla: int | None = 42
    tiempo_ciclo_seg: float = 1800.0  # tiempo entre ensambles
    tiempo_ciclo_sigma: float = 240.0
    inicio: str = "2026-11-10T06:00:00"
    reloj: str = "simulado"  # simulado | real
    vida_herramienta: int = 300  # piezas de un mismo componente por herramienta
    tamano_lote: int = 50
    linea: str = "ENSAMBLE-BRAZO"
    operadores: list[str] = field(
        default_factory=lambda: ["A. Ruiz", "M. Torres", "J. Salas", "L. Mendez"]
    )

    def __post_init__(self) -> None:
        if self.conjuntos < 0:
            raise ValueError("'conjuntos' no puede ser negativo")
        if self.tiempo_ciclo_seg <= 0:
            raise ValueError("'tiempo_ciclo_seg' debe ser mayor que 0")
        if self.vida_herramienta <= 0:
            raise ValueError("'vida_herramienta' debe ser mayor que 0")
        if self.tamano_lote <= 0:
            raise ValueError("'tamano_lote' debe ser mayor que 0")
        if not self.operadores:
            raise ValueError("Debe haber al menos un operador")
        if self.reloj not in ("simulado", "real"):
            raise ValueError(
                "'reloj' debe ser 'simulado' (avanza 30 min por ensamble) "
                "o 'real' (usa la hora del equipo)"
            )


# ---------------------------------------------------------------------------
# Causas de defecto
# ---------------------------------------------------------------------------
@dataclass
class Defectos:
    escala: float = 1.0
    probabilidad_base: float = 0.0001
    sigmas_atipico_min: float = 4.0
    sigmas_atipico_max: float = 9.0
    probabilidad_evento: float = 0.0008
    probabilidad_cota_en_evento: float = 0.35
    sigmas_evento_min: float = 2.5
    sigmas_evento_max: float = 6.0
    probabilidad_error_medicion: float = 0.00015
    error_bandas_min: float = 0.6
    error_bandas_max: float = 1.5
    multiplicador_sigma: float = 1.0
    deriva_total_sigmas: float = 0.6

    def __post_init__(self) -> None:
        for nombre in (
            "probabilidad_base",
            "probabilidad_evento",
            "probabilidad_cota_en_evento",
            "probabilidad_error_medicion",
        ):
            valor = getattr(self, nombre)
            if not 0.0 <= valor <= 1.0:
                raise ValueError(f"'{nombre}' debe estar entre 0 y 1")
        if self.escala < 0:
            raise ValueError("'escala' no puede ser negativa")
        if self.multiplicador_sigma <= 0:
            raise ValueError("'multiplicador_sigma' debe ser mayor que 0")
        if self.sigmas_atipico_min > self.sigmas_atipico_max:
            raise ValueError("'sigmas_atipico_min' no puede superar al máximo")


@dataclass
class ParametrosMaquina:
    """Condiciones de la estación de trabajo (covariables simples)."""

    temperatura_ref: float = 20.0
    temperatura_sigma: float = 1.5
    calentamiento_max: float = 3.0
    piezas_calentamiento: int = 50

    def __post_init__(self) -> None:
        if self.piezas_calentamiento < 0:
            raise ValueError("'piezas_calentamiento' no puede ser negativo")


@dataclass
class Salida:
    carpeta: str = "datos"
    separador: str = ";"
    incluir_mediciones: bool = True
    incluir_parquet: bool = False


# ---------------------------------------------------------------------------
# Configuración completa
# ---------------------------------------------------------------------------
@dataclass
class Config:
    componentes: list[Componente]
    proceso: Proceso = field(default_factory=Proceso)
    defectos: Defectos = field(default_factory=Defectos)
    parametros: ParametrosMaquina = field(default_factory=ParametrosMaquina)
    salida: Salida = field(default_factory=Salida)

    def validar(self) -> "Config":
        if not self.componentes:
            raise ValueError("El catálogo no tiene componentes")
        if len(self.salida.separador) != 1:
            raise ValueError("'salida.separador' debe ser un único carácter")
        for componente in self.componentes:
            if not componente.cotas:
                raise ValueError(f"El componente {componente.codigo} no tiene cotas")
        codigos = [c.codigo for c in self.cotas]
        repetidos = {c for c in codigos if codigos.count(c) > 1}
        if repetidos:
            raise ValueError(f"Códigos de cota repetidos: {sorted(repetidos)}")
        return self

    @property
    def cotas(self) -> list[Cota]:
        return [c for componente in self.componentes for c in componente.cotas]

    def componente(self, codigo: str) -> Componente:
        for c in self.componentes:
            if c.codigo == codigo:
                return c
        raise KeyError(f"No existe el componente {codigo!r}")


# ---------------------------------------------------------------------------
# Catálogo en CSV
# ---------------------------------------------------------------------------
def escribir_catalogo(config: Config, ruta: str | Path) -> Path:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.writer(archivo, delimiter=";")
        escritor.writerow(COLUMNAS_CATALOGO)
        for componente in config.componentes:
            for cota in componente.cotas:
                escritor.writerow(
                    [
                        componente.id,
                        componente.codigo,
                        componente.nombre,
                        cota.codigo,
                        cota.nombre,
                        cota.tipo,
                        f"{cota.nominal:g}",
                        f"{cota.tol_inf:g}",
                        f"{cota.tol_sup:g}",
                        cota.unidad,
                        f"{cota.cpk_objetivo:g}",
                        cota.decimales,
                    ]
                )
    return ruta


def leer_catalogo(ruta: str | Path) -> list[Componente]:
    ruta = Path(ruta)
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el catálogo de cotas: {ruta}")

    with ruta.open(encoding="utf-8-sig", newline="") as archivo:
        primera = archivo.readline()
        archivo.seek(0)
        separador = ";" if ";" in primera else ","
        filas = list(csv.DictReader(archivo, delimiter=separador))
    if not filas:
        raise ValueError(f"El catálogo {ruta} está vacío")

    componentes: dict[str, Componente] = {}
    for numero, fila in enumerate(filas, start=2):
        try:
            tipo = normalizar_tipo(fila["tipo"])
            perfil = PERFILES[tipo]
            codigo_pieza = fila["codigo_pieza"].strip()
            componente = componentes.get(codigo_pieza)
            if componente is None:
                componente = Componente(
                    id=int(fila["id_pieza"]),
                    codigo=codigo_pieza,
                    nombre=fila["nombre_pieza"].strip(),
                )
                componentes[codigo_pieza] = componente

            cpk_texto = (fila.get("cpk_objetivo") or "").strip()
            decimales_texto = (fila.get("decimales") or "").strip()
            unidad_texto = (fila.get("unidad") or "").strip()

            componente.cotas.append(
                Cota(
                    codigo=fila["codigo_cota"].strip(),
                    nombre=fila["nombre_cota"].strip(),
                    tipo=tipo,
                    nominal=_numero(fila["nominal"]),
                    tol_inf=_numero(fila["tol_inf"]),
                    tol_sup=_numero(fila["tol_sup"]),
                    unidad=unidad_texto or perfil["unidad"],
                    decimales=int(decimales_texto) if decimales_texto else perfil["decimales"],
                    cpk_objetivo=float(cpk_texto) if cpk_texto else perfil["cpk"],
                    carga_comun=perfil["carga_comun"],
                    factor_deriva=perfil["deriva"],
                )
            )
        except KeyError as error:
            raise ValueError(f"Falta la columna {error} en la fila {numero} de {ruta}") from error
        except (TypeError, ValueError) as error:
            raise ValueError(f"Fila {numero} de {ruta}: {error}") from error

    return list(componentes.values())


# ---------------------------------------------------------------------------
# proceso.json
# ---------------------------------------------------------------------------
def _desde_dict(clase: type, datos: dict[str, Any]) -> Any:
    if not isinstance(datos, dict):
        raise TypeError(f"Se esperaba un objeto para {clase.__name__}")
    tipos = get_type_hints(clase)
    valores: dict[str, Any] = {}
    for campo in fields(clase):
        if campo.name not in datos:
            continue
        valor = datos[campo.name]
        tipo = tipos[campo.name]
        if is_dataclass(tipo):
            valor = _desde_dict(tipo, valor)
        elif get_origin(tipo) is list:
            (subtipo,) = get_args(tipo)
            if is_dataclass(subtipo):
                valor = [_desde_dict(subtipo, v) for v in valor]
        valores[campo.name] = valor
    return clase(**valores)


def guardar_config(config: Config, carpeta: str | Path) -> dict[str, Path]:
    """Escribe catálogo y parámetros en la carpeta indicada."""
    destino = Path(carpeta)
    destino.mkdir(parents=True, exist_ok=True)
    ruta_catalogo = escribir_catalogo(config, destino / "catalogo_cotas.csv")
    ruta_proceso = destino / "proceso.json"
    ruta_proceso.write_text(
        json.dumps(
            {
                "proceso": _a_dict(config.proceso),
                "defectos": _a_dict(config.defectos),
                "parametros": _a_dict(config.parametros),
                "salida": _a_dict(config.salida),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return {"catalogo": ruta_catalogo, "proceso": ruta_proceso}


def _a_dict(objeto: Any) -> dict[str, Any]:
    from dataclasses import asdict

    return asdict(objeto)


def cargar_config(carpeta: str | Path) -> Config:
    """Carga `catalogo_cotas.csv` y `proceso.json` de una carpeta."""
    carpeta = Path(carpeta)
    ruta_catalogo = carpeta / "catalogo_cotas.csv"
    ruta_proceso = carpeta / "proceso.json"

    componentes = leer_catalogo(ruta_catalogo)
    datos = json.loads(ruta_proceso.read_text(encoding="utf-8")) if ruta_proceso.exists() else {}

    config = Config(
        componentes=componentes,
        proceso=_desde_dict(Proceso, datos.get("proceso", {})),
        defectos=_desde_dict(Defectos, datos.get("defectos", {})),
        parametros=_desde_dict(ParametrosMaquina, datos.get("parametros", {})),
        salida=_desde_dict(Salida, datos.get("salida", {})),
    )
    return config.validar()


# ---------------------------------------------------------------------------
# Configuración por defecto: ensamble del brazo de retroexcavadora
# ---------------------------------------------------------------------------
def config_por_defecto() -> Config:
    """Construye la configuración a partir del catálogo semilla."""
    por_pieza: dict[str, Componente] = {}
    for (
        id_pieza,
        codigo_pieza,
        nombre_pieza,
        codigo_cota,
        nombre_cota,
        tipo,
        nominal,
        tol_inf,
        tol_sup,
    ) in SEED:
        componente = por_pieza.get(codigo_pieza)
        if componente is None:
            componente = Componente(id=id_pieza, codigo=codigo_pieza, nombre=nombre_pieza)
            por_pieza[codigo_pieza] = componente
        perfil = PERFILES[normalizar_tipo(tipo)]
        componente.cotas.append(
            Cota(
                codigo=codigo_cota,
                nombre=nombre_cota,
                tipo=tipo,
                nominal=nominal,
                tol_inf=tol_inf,
                tol_sup=tol_sup,
                unidad=perfil["unidad"],
                decimales=perfil["decimales"],
                cpk_objetivo=perfil["cpk"],
                carga_comun=perfil["carga_comun"],
                factor_deriva=perfil["deriva"],
            )
        )

    return Config(componentes=list(por_pieza.values())).validar()
