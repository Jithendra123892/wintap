"""Features for one tap window (N x 3 gyro + N x 3 accel, high-passed, trigger at TRIG).

Everything is normalised by tap strength so a soft and a firm tap in the same zone look alike;
the sign of the twist at its peak is what should separate left from right, and the gyro/accel
ratio and decay shape what should separate top from bottom.
"""

import numpy as np

from .detector import FS, N, TRIG

TEMPLATE_LEN, TEMPLATE_STEP = 64, 4  # 80 ms of waveform shape, sampled every 5 ms
BANDS = [(0, 40), (40, 80), (80, 160), (160, 400)]
_N_TPL = (TEMPLATE_LEN // TEMPLATE_STEP) * 3
_N_HAND = 3 + 3 + 3 + 3 + 3 + 2 + 1 + len(BANDS)
N_FEATURES = _N_HAND + _N_TPL
# Per-feature weights applied after standardisation, so the long waveform template does not
# drown the hand-made features in distance-based models.
WEIGHTS = np.concatenate([np.ones(_N_HAND), np.full(_N_TPL, 0.35)])


def _bands(x):
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    freqs = np.fft.rfftfreq(len(x), 1 / FS)
    e = np.array([spec[(freqs >= lo) & (freqs < hi)].sum() for lo, hi in BANDS]) + 1e-12
    return np.log(e / e.sum())


def onset(gm):
    """First sample at 25% of the window's peak twist: the tap's start, independent of the trigger threshold."""
    span = gm[:120]
    peak = span.max()
    if peak <= 0:
        return TRIG
    return int(np.argmax(span >= 0.25 * peak))


def extract(g, a):
    g = np.asarray(g, float)
    a = np.asarray(a, float)
    gm = np.linalg.norm(g, axis=1)
    am = np.linalg.norm(a, axis=1)
    o = onset(gm)
    k = o + int(np.argmax(gm[o: o + 64]))
    gp = max(gm[k], 1e-6)
    ka = max(o - 8, 0) + int(np.argmax(am[max(o - 8, 0): o + 64]))
    ap = max(am[ka], 1e-9)

    early = g[max(o - 8, 0): o + 32]
    e_g = (g ** 2).sum(0) + 1e-12
    e_a = (a ** 2).sum(0) + 1e-12
    below = np.nonzero(gm[k:] < 0.25 * gp)[0]
    decay_ms = (below[0] if len(below) else N - k) / FS * 1000

    tpl = g[k - 8: k - 8 + TEMPLATE_LEN: TEMPLATE_STEP] if k >= 8 else g[:TEMPLATE_LEN:TEMPLATE_STEP]
    tpl = np.vstack([tpl, np.zeros((TEMPLATE_LEN // TEMPLATE_STEP - len(tpl), 3))]) / gp

    return np.concatenate([
        g[k] / gp,                                   # twist direction at its peak (signed)
        early.sum(0) / (np.abs(early).sum() + 1e-9),  # net early rotation per axis (signed)
        e_g / e_g.sum(),                             # how twist energy splits across axes
        a[ka] / ap,                                  # shake direction at its peak (signed)
        e_a / e_a.sum(),                             # how shake energy splits across axes
        [np.log(gp / ap), np.log(gp)],               # twist per unit shake; tap strength
        [decay_ms / 50.0],
        _bands(gm),
        tpl.ravel(),
    ])


# Feature definitions for CLI and web UI
FEATURE_CATEGORIES = {
    "core": {
        "label": "Core Features",
        "desc": "Essential features for basic tap classification",
        "default": True,
        "features": [
            {"name": "twist_direction", "label": "Twist Direction", "desc": "Gyro twist at peak", "importance": "essential", "default": True, "index": 0},
            {"name": "early_rotation", "label": "Early Rotation", "desc": "Net early rotation per axis", "importance": "essential", "default": True, "index": 1},
            {"name": "gyro_energy", "label": "Gyro Energy Split", "desc": "How twist energy splits across axes", "importance": "essential", "default": True, "index": 2},
            {"name": "shake_direction", "label": "Shake Direction", "desc": "Accel shake direction at peak", "importance": "essential", "default": True, "index": 3},
            {"name": "accel_energy", "label": "Accel Energy Split", "desc": "How shake energy splits across axes", "importance": "essential", "default": True, "index": 4},
            {"name": "twist_shake_ratio", "label": "Twist/Shake Ratio", "desc": "Twist per unit shake", "importance": "essential", "default": True, "index": 5},
            {"name": "tap_strength", "label": "Tap Strength", "desc": "log(gyro peak)", "importance": "useful", "default": True, "index": 6},
            {"name": "decay_time", "label": "Decay Time", "desc": "Signal decay time normalized", "importance": "useful", "default": True, "index": 7},
        ],
    },
    "spectral": {
        "label": "Spectral Features",
        "desc": "Frequency-domain features for distinguishing tap types",
        "default": True,
        "features": [
            {"name": "spectral_band_0", "label": "Band 0-40Hz", "desc": "Low frequency energy", "importance": "useful", "default": True, "index": 8},
            {"name": "spectral_band_1", "label": "Band 40-80Hz", "desc": "Mid-low frequency energy", "importance": "useful", "default": True, "index": 9},
            {"name": "spectral_band_2", "label": "Band 80-160Hz", "desc": "Mid frequency energy", "importance": "experimental", "default": True, "index": 10},
            {"name": "spectral_band_3", "label": "Band 160-400Hz", "desc": "High frequency energy", "importance": "experimental", "default": True, "index": 11},
            {"name": "spectral_band_4", "label": "Band 0-20Hz", "desc": "Very low frequency", "importance": "useful", "default": False, "index": 12},
            {"name": "spectral_band_5", "label": "Band 20-40Hz", "desc": "Sub low frequency", "importance": "useful", "default": False, "index": 13},
            {"name": "spectral_band_6", "label": "Band 120-160Hz", "desc": "Upper mid frequency", "importance": "experimental", "default": False, "index": 14},
            {"name": "spectral_band_7", "label": "Band 160-200Hz", "desc": "High-mid frequency", "importance": "experimental", "default": False, "index": 15},
            {"name": "spectral_band_8", "label": "Band 200-300Hz", "desc": "Upper frequency", "importance": "experimental", "default": False, "index": 16},
            {"name": "spectral_band_9", "label": "Band 300-400Hz", "desc": "Very high frequency", "importance": "experimental", "default": False, "index": 17},
            {"name": "spectrogram_peak_1", "label": "Spec Peak 1", "desc": "Spectrogram max 1", "importance": "useful", "default": True, "index": 18},
            {"name": "spectrogram_peak_2", "label": "Spec Peak 2", "desc": "Spectrogram max 2", "importance": "useful", "default": True, "index": 19},
        ],
    },
    "template": {
        "label": "Template Features",
        "desc": "Raw waveform templates for pattern matching",
        "default": False,
        "features": [
            {"name": "gyro_template", "label": "Gyro Template", "desc": "Gyro waveform template (48 values)", "importance": "experimental", "default": False, "index": 20},
            {"name": "combined_template", "label": "Combined Template", "desc": "Gyro+accel combined (96 values)", "importance": "experimental", "default": False, "index": 21},
        ],
    },
}

# Flattened feature list for index mapping
FEATURE_METADATA = []
for category_name, category_data in FEATURE_CATEGORIES.items():
    for feat in category_data["features"]:
        FEATURE_METADATA.append({
            **feat,
            "category": category_name,
            "category_label": category_data["label"],
        })

# Feature name to index mapping
FEATURE_INDEX = {f["name"]: f["index"] for f in FEATURE_METADATA}

# Default enabled features (all essential + useful by default)
DEFAULT_ENABLED_FEATURES = [f["name"] for f in FEATURE_METADATA if f["default"]]

def get_feature_by_name(name):
    """Look up feature metadata by name."""
    return FEATURE_METADATA[FEATURE_INDEX.get(name)] if name in FEATURE_INDEX else None
