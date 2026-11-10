"""La distribución de cada estadística es coherente: cuantiles, probabilidades y media cuadran."""
import numpy as np

import distribucion as dist

DISP = (1.5, 0.6)


def test_cuantiles_ordenados_y_enteros():
    mu = np.array([0.3, 2.0, 11.0, 27.5])
    Q = np.column_stack([dist.cuantil(mu, DISP, q) for q in dist.REJILLA])
    assert (np.diff(Q, axis=1) >= 0).all()
    assert np.allclose(Q, np.round(Q))


def test_prob_mayor_cuadra_con_la_pmf_y_la_media():
    mu = 18.4
    p = dist.pmf(mu, DISP, 200)
    assert np.isclose(p.sum(), 1.0, atol=1e-6)
    assert np.isclose((p * np.arange(201)).sum(), mu, atol=1e-3)
    assert np.isclose(dist.prob_mayor(np.array([mu]), DISP, 24.5)[0], p[25:].sum(), atol=1e-6)
    assert np.isclose(dist.prob_mayor(np.array([mu]), DISP, 24.5)[0], dist.prob_mayor(np.array([mu]), DISP, 24)[0])


def test_la_dispersion_se_recupera_de_datos_simulados():
    rng = np.random.default_rng(0)
    mu = rng.uniform(2, 25, 20000)
    r = dist.r_de(mu, DISP)
    y = rng.negative_binomial(r, r / (r + mu)).astype(float)
    a, b = dist.ajustar_dispersion(y, mu)
    assert abs(a - DISP[0]) < 0.25 and abs(b - DISP[1]) < 0.12


def test_recalibrar_corrige_una_dispersion_equivocada():
    """Si la NB se ajusta con la dispersión mal, el mapa del PIT devuelve la cobertura correcta."""
    rng = np.random.default_rng(1)
    mu = rng.uniform(3, 20, 30000)
    r = dist.r_de(mu, DISP)
    y = rng.negative_binomial(r, r / (r + mu)).astype(float)
    mala = (DISP[0] - 1.2, DISP[1])                        # cola demasiado larga
    recal = dist.ajustar_recalibracion(y[:15000], mu[:15000], mala)
    lo, hi = (dist.cuantil(mu[15000:], mala, q, recal) for q in (0.1, 0.9))
    lo0, hi0 = (dist.cuantil(mu[15000:], mala, q) for q in (0.1, 0.9))
    ancho, ancho0 = (hi - lo).mean(), (hi0 - lo0).mean()
    assert ancho < ancho0                                  # el intervalo se angosta hacia el correcto
    p = dist.pmf(9.0, mala, 300, recal)
    assert np.isclose(p.sum(), 1.0, atol=1e-6) and (p >= -1e-12).all()
