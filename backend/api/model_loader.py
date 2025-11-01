# api/model_loader.py (potongan pengganti fungsi _build_efficientnet_b0 & load)
import json, os, torch, torch.nn as nn
from torchvision import models
from django.conf import settings

_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
_model = None
_class_names = None
_img_size = 224

def _build_efficientnet_b0_variant(num_classes: int, nested_head: bool) -> nn.Module:
    """
    nested_head=True  -> cocok utk checkpoint dg key 'classifier.1.1.weight' (double-dropout head)
    nested_head=False -> head klasik: Sequential(Dropout, Linear) langsung di classifier
    """
    m = models.efficientnet_b0(weights=None)
    in_feats = m.classifier[1].in_features
    if nested_head:
        # Pertahankan Dropout di [0], lalu [1] = Sequential(Dropout, Linear)
        m.classifier[1] = nn.Sequential(
            nn.Dropout(p=0.2, inplace=True),
            nn.Linear(in_feats, num_classes)
        )
    else:
        # Ganti seluruh classifier dengan (Dropout, Linear)
        m.classifier = nn.Sequential(
            nn.Dropout(p=0.2, inplace=True),
            nn.Linear(in_feats, num_classes)
        )
    return m

def get_model_and_meta():
    global _model, _class_names, _img_size
    if _model is not None:
        return _model, _class_names, _img_size, _device

    ckpt_path = settings.CKPT_PATH
    labels_json = settings.LABELS_JSON

    # Gunakan weights_only=False eksplisit (sesuai warning PyTorch)
    ckpt = torch.load(ckpt_path, map_location=_device, weights_only=False)

    if isinstance(ckpt, dict) and "model_state" in ckpt:
        state = ckpt["model_state"]
        _class_names = ckpt.get("class_names")
        if _class_names is None and labels_json and os.path.exists(labels_json):
            with open(labels_json, "r", encoding="utf-8") as f:
                _class_names = json.load(f)
        if _class_names is None:
            raise RuntimeError("class_names tidak ditemukan di ckpt dan labels.json.")

        _img_size = int(ckpt.get("img_size", 224))

        # DETEKSI pola key
        has_nested = any(k.startswith("classifier.1.1.") for k in state.keys())
        _model = _build_efficientnet_b0_variant(len(_class_names), nested_head=has_nested)

        # Muat state_dict secara strict (cocokkan arsitektur)
        _model.load_state_dict(state, strict=True)

    elif hasattr(ckpt, "state_dict"):
        # full-model
        _model = ckpt
        with open(labels_json, "r", encoding="utf-8") as f:
            _class_names = json.load(f)
        _img_size = getattr(_model, "img_size", 224)
    else:
        raise RuntimeError("Format checkpoint tidak dikenali.")

    _model = _model.to(_device).eval()
    return _model, _class_names, _img_size, _device
