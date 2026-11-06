"""Enhanced features for one tap window (N x 3 gyro + N x 3 accel, high-passed, trigger at TRIG).

Enhanced version with pressure awareness, spectrogram features, and better bump discrimination.
Made for Wintap - Windows lid tap detector that exceeds Apple's Touch experience.
"""

import numpy as np

from .detector import FS, N, TRIG

TEMPLATE_LEN, TEMPLATE_STEP = 64, 4  # 80 ms of waveform shape, sampled every 5 ms
BANDS = [(0, 40), (40, 80), (80, 160), (160, 400)]
BANDS_EXT = [(0, 20), (20, 40), (40, 80), (80, 120), (120, 160), (160, 200), (200, 300), (300, 400)]

# Feature template sizes
_N_TPL = 48 + 96  # gyro template (48) + combined gyro+accel template (96)
_N_HAND = 42      # core hand features
N_FEATURES = 186  # computed from extract() output


def _bands(x):
    """Spectral bands for frequency analysis."""
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    freqs = np.fft.rfftfreq(len(x), 1 / FS)
    e = np.array([spec[(freqs >= lo) & (freqs < hi)].sum() for lo, hi in BANDS_EXT]) + 1e-12
    return np.log(e / e.sum())


def _spectrogram_features(x, n_bands=12):
    """Short-time frequency analysis for tap signature distinguishing genuine taps from bumps."""
    n = len(x)
    band_size = max(1, n // n_bands)
    features = []
    for i in range(0, n - band_size + 1, band_size // 2):
        window = x[i:i+band_size] * np.hanning(band_size)
        spec = np.abs(np.fft.rfft(window)) ** 2
        features.append(float(spec.max()) if len(spec) > 0 else 0.0)
    while len(features) < n_bands:
        features.append(0.0)
    return np.array(features[:n_bands])


def onset(gm):
    """First sample at 25% of the window's peak twist: the tap's start, independent of the trigger threshold."""
    span = gm[:120]
    peak = span.max()
    if peak <= 0:
        return TRIG
    return int(np.argmax(span >= 0.25 * peak))


def decay_features(signal, peak_idx, rise_idx):
    """Analyze signal decay after peak for bump discrimination."""
    peak_val = signal[peak_idx] if peak_idx < len(signal) else signal[-1]
    if peak_val <= 0:
        peak_val = 1e-6
    after = signal[peak_idx:]
    above_25 = np.where(after >= 0.25 * peak_val)[0]
    if len(above_25) > 1:
        decay_idx = above_25[-1]
    else:
        decay_idx = 0
    before_peak = signal[max(0, peak_idx-10):peak_idx]
    after_peak = signal[peak_idx:min(len(signal), peak_idx+50)]
    rise_energy = np.sum(before_peak ** 2)
    decay_energy = np.sum(after_peak ** 2)
    asymmetry = (decay_energy - rise_energy) / (decay_energy + rise_energy + 1e-9)
    return decay_idx / FS * 1000, asymmetry


def extract(g, a):
    """Extract enhanced features from gyro and accel windows.

    Features designed to distinguish lid taps from desk bumps:
    - Gyro twist pattern (distinguishes tap from translation)
    - Accelerometer magnitude (pressure signature)
    - Asymmetry features (rise vs decay shape)
    - Spectral bands (tap signature fingerprint)
    - Combined templates for ML classification
    """
    g = np.asarray(g, float)
    a = np.asarray(a, float)
    gm = np.linalg.norm(g, axis=1)
    am = np.linalg.norm(a, axis=1)

    o = onset(gm)
    k = o + int(np.argmax(gm[o: o + 64]))
    gp = max(gm[k], 1e-6)
    ka = max(o - 8, 0) + int(np.argmax(am[max(o - 8, 0): o + 64]))
    ap = max(am[ka], 1e-9)

    # Peak acceleration (pressure) features
    peak_ap = np.sqrt((a[ka]**2).sum())
    peak_a_dir = a[ka] / (peak_ap + 1e-9)

    early = g[max(o - 8, 0): o + 32]
    e_g = (g ** 2).sum(0) + 1e-12
    e_a = (a ** 2).sum(0) + 1e-12
    below = np.nonzero(gm[k:] < 0.25 * gp)[0]
    decay_ms = (below[0] if len(below) else N - k) / FS * 1000

    # Rise time analysis
    rise_idx = np.argmax(gm[:k+1]) if k > 0 else 0
    rise_ms = rise_idx / FS * 1000

    # Decay features for bump discrimination
    decay_time, asymmetry = decay_features(gm, k, rise_idx)

    # Templates normalized by their respective peak magnitudes
    tpl_g_start = max(0, k - 8)
    tpl_g = g[tpl_g_start: tpl_g_start + TEMPLATE_LEN: TEMPLATE_STEP]
    tpl_g = np.vstack([tpl_g, np.zeros((TEMPLATE_LEN // TEMPLATE_STEP - len(tpl_g), 3))]) / gp

    # Accel template captures pressure signature
    tpl_a_start = max(0, ka - 8)
    tpl_a = a[tpl_a_start: tpl_a_start + TEMPLATE_LEN: TEMPLATE_STEP]
    if len(tpl_a) < TEMPLATE_LEN // TEMPLATE_STEP:
        tpl_a = np.vstack([tpl_a, np.zeros((TEMPLATE_LEN // TEMPLATE_STEP - len(tpl_a), 3))])
    tpl_a = tpl_a / (peak_ap + 1e-9)

    # Combined template for richer characterization
    n_tpl = TEMPLATE_LEN // TEMPLATE_STEP
    tpl_combined = []
    for i in range(n_tpl):
        if i < len(tpl_g):
            tpl_combined.extend(tpl_g[i])
        else:
            tpl_combined.extend([0, 0, 0])
        if i < len(tpl_a):
            tpl_combined.extend(tpl_a[i])
        else:
            tpl_combined.extend([0, 0, 0])
    tpl_combined = np.array(tpl_combined)

    return np.concatenate([
        g[k] / gp,                                   # twist direction at peak
        early.sum(0) / (np.abs(early).sum() + 1e-9),  # net early rotation per axis
        e_g / e_g.sum(),                             # gyro energy split
        a[ka] / ap,                                  # shake direction at peak
        e_a / e_a.sum(),                             # accel energy split
        [np.log(gp / ap), np.log(gp)],               # twist/shake ratio, strength
        [decay_ms / 50.0],                           # decay time normalized
        [rise_ms / 100.0],                           # rise time normalized
        [asymmetry],                                 # rise/decay asymmetry
        _bands(gm),                                  # extended spectral bands
        _spectrogram_features(gm),                   # spectrogram signature
        peak_a_dir.ravel()[:3],                      # peak acceleration direction
        [peak_ap],                                   # peak acceleration (pressure)
        tpl_g.ravel(),                               # gyro template
        tpl_combined,                                # combined template
    ])


# Weights: hand-crafted features weighted higher, templates lower
# Actual computation: run extract() to get real feature count
def _get_weights():
    """Compute weights array matching the actual feature count from extract()."""
    # Use a known valid input size
    try:
        gm = np.zeros(160)
        g = np.zeros((160, 3))
        a = np.zeros((160, 3))
        feat_len = len(extract(g, a))
        w = np.full(feat_len, 1.0)
        w[42:] = 0.25  # templates get lower weight
        return w
    except:
        return np.full(210, 1.0)  # fallback estimate


WEIGHTS = _get_weights()
N_FEATURES = len(WEIGHTS)