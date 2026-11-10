"""Distribución completa de cada estadística de conteo: media + dispersión -> binomial negativa.

En vez de tres cuantiles sueltos (q10, q50, q90), cada jugador-estadística recibe una
distribución discreta completa. De ahí sale todo lo demás, coherente entre sí:
  - la media (lo que se suma para armar el total del equipo; la mediana no se puede sumar)
  - la mediana y cualquier cuantil (enteros: nadie anota 23.1 puntos)
  - P(estadística > X) para cualquier X

Modelo:
  media          LightGBM con objetivo Poisson (mismos features e hiperparámetros que el v2)
  dispersión     varianza = mu + mu^2 / r, con log r = a + b·log mu. a y b se ajustan por máxima
                 verosimilitud en la temporada de calibración (que el modelo de la media no vio).
                 r grande = Poisson; r chico = cola más larga (puntos, tiros libres).
  recalibración  la binomial negativa no es la forma exacta de ninguna estadística. En la misma
                 temporada de calibración se mide el PIT (en qué percentil de su distribución cayó
                 cada resultado) y se corrige: si lo que la NB llama "percentil 90" resulta ser el
                 88.9, se usa el 88.9. Es el equivalente, para toda la distribución, del ajuste
                 conformal que el v2 hacía solo en los dos extremos.

Resultados (nov 2026, exp/dist2.py; pérdida de cuantiles en q10/q50/q90, menor es mejor):
                  2025-26            2026-27 en vivo
                  v2      NB         v2      NB
  puntos          1.4050  1.4017     1.3875  1.3855
  rebotes         0.5773  0.5741     0.5737  0.5701
  asistencias     0.4052  0.3993     0.4087  0.3996
  triples         0.2597  0.2556     0.2574  0.2522
  robos           0.2028  0.1996     0.2019  0.1993
En las 15 estadísticas de conteo (results/banco_dist_15.csv): mejor pérdida de cuantiles en
15 de 15 en las dos canchas; mejor error absoluto de la mediana en 15 de 15 en 2025-26 y en 14
de 15 en vivo (puntos queda igual: 4.427 -> 4.431). La media sale sin sesgo (puntos -0.05 en
2025-26; la mediana del v2 subestimaba 0.71).
Los cuantiles "continuos" (interpolados entre enteros) salieron peor que los enteros: descartados.

Solo para conteos. Los minutos no son un conteo: siguen con sus cuantiles de LightGBM."""
import numpy as np
import pandas as pd
import lightgbm as lgb
from scipy import optimize, stats
from scipy.special import gammaln

from models import PARAMS

REJILLA = [round(q, 2) for q in np.arange(0.05, 0.96, 0.05)]


def entrenar_media(fit: pd.DataFrame, cols: list, obj: str) -> lgb.LGBMRegressor:
    m = lgb.LGBMRegressor(objective="poisson", **PARAMS)
    m.fit(fit[cols], fit[f"y_{obj}"].clip(lower=0))
    return m


def _nll(theta, y, mu):
    a, b = theta
    r = np.exp(np.clip(a + b * np.log(mu), -4, 8))
    return -(gammaln(y + r) - gammaln(r) - gammaln(y + 1)
             + r * np.log(r / (r + mu)) + y * np.log(mu / (r + mu))).mean()


def ajustar_dispersion(y: np.ndarray, mu: np.ndarray) -> tuple:
    """(a, b) de log r = a + b·log mu, por máxima verosimilitud."""
    mu = np.clip(mu, 1e-3, None)
    res = optimize.minimize(_nll, x0=[2.0, 0.5], args=(y, mu), method="Nelder-Mead",
                            options={"xatol": 1e-4, "fatol": 1e-7, "maxiter": 2000})
    return float(res.x[0]), float(res.x[1])


REJILLA_PIT = np.linspace(0, 1, 101)


def _cdf(k, mu, r):
    return stats.nbinom.cdf(k, r, r / (r + mu))


def ajustar_recalibracion(y: np.ndarray, mu: np.ndarray, disp: tuple, semilla: int = 0) -> np.ndarray:
    """Mapa nivel real -> nivel de la NB, en 101 puntos. PIT aleatorizado: en un conteo el
    resultado k ocupa todo el tramo de F(k-1) a F(k), y se sortea un punto dentro."""
    mu = np.clip(mu, 1e-3, None)
    r = r_de(mu, disp)
    hi, lo = _cdf(y, mu, r), _cdf(y - 1, mu, r)
    pit = lo + np.random.default_rng(semilla).uniform(size=len(y)) * (hi - lo)
    mapa = np.quantile(pit, REJILLA_PIT)
    mapa[0], mapa[-1] = 0.0, 1.0
    return np.maximum.accumulate(mapa)


def r_de(mu: np.ndarray, disp: tuple) -> np.ndarray:
    return np.exp(np.clip(disp[0] + disp[1] * np.log(np.clip(mu, 1e-3, None)), -4, 8))


def cuantil(mu: np.ndarray, disp: tuple, q: float, recal: np.ndarray = None) -> np.ndarray:
    mu = np.clip(mu, 1e-3, None)
    r = r_de(mu, disp)
    if recal is not None:
        q = float(np.interp(q, REJILLA_PIT, recal))          # el nivel que hay que pedirle a la NB
    return stats.nbinom.ppf(q, r, r / (r + mu))


def prob_mayor(mu: np.ndarray, disp: tuple, x: float, recal: np.ndarray = None) -> np.ndarray:
    """P(estadística > x). Con x = 24.5 es la probabilidad de 25 o más."""
    mu = np.clip(mu, 1e-3, None)
    r = r_de(mu, disp)
    F = _cdf(np.floor(x), mu, r)
    if recal is not None:
        F = np.interp(F, recal, REJILLA_PIT)                  # nivel de la NB -> nivel real
    return 1 - F


def pmf(mu: float, disp: tuple, hasta: int, recal: np.ndarray = None) -> np.ndarray:
    """P(X = 0), ..., P(X = hasta) de un jugador-estadística."""
    k = np.arange(-1, hasta + 1)
    sobrevive = prob_mayor(np.full(len(k), float(mu)), disp, k, recal)
    sobrevive[0] = 1.0
    return -np.diff(sobrevive)


# ---------------------------------------------------------------- como modelo del banco
def modelo_nb(fit, calib, test, cols, objetivos) -> pd.DataFrame:
    """Media Poisson + dispersión NB + recalibración. Devuelve mediana, la rejilla completa y la media."""
    out = pd.DataFrame(index=test.index)
    for obj in objetivos:
        if obj == "numMinutes":
            continue
        m = entrenar_media(fit, cols, obj)
        yc, muc = calib[f"y_{obj}"].to_numpy(float), m.predict(calib[cols])
        disp = ajustar_dispersion(yc, muc)
        recal = ajustar_recalibracion(yc, muc, disp)
        mu = m.predict(test[cols])
        out[f"{obj}_media"] = mu
        for q in REJILLA:
            out[f"{obj}_q{int(round(q * 100)):02d}"] = cuantil(mu, disp, q, recal)
        out[obj] = out[f"{obj}_q50"]
        print(f"    {obj}: log r = {disp[0]:+.2f} {disp[1]:+.2f}·log mu | niveles 10/50/90 -> "
              f"{recal[10]:.3f}/{recal[50]:.3f}/{recal[90]:.3f}")
    return out
