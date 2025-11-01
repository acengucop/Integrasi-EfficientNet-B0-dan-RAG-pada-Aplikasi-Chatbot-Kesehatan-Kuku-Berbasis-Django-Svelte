# api/inference.py
import io
import numpy as np
from PIL import Image, ImageOps
import torch
from torchvision import transforms
from .model_loader import get_model_and_meta

def _build_tfms(img_size: int):
    return transforms.Compose([
        transforms.Resize((img_size, img_size)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225]),
    ])

@torch.inference_mode()
def predict_image(pil_img, tta=True):
    model, class_names, img_size, device = get_model_and_meta()
    tfms = _build_tfms(img_size)

    # pastikan RGB
    pil_img = pil_img.convert("RGB")
    x = tfms(pil_img).unsqueeze(0).to(device, non_blocking=True)
    if device.type == "cuda":
        with torch.amp.autocast(device_type="cuda"):
            logits = model(x)
    else:
        logits = model(x)
    probs = torch.softmax(logits, dim=1).cpu().numpy().squeeze()

    if tta:
        pil_hf = ImageOps.mirror(pil_img)
        x_hf = tfms(pil_hf).unsqueeze(0).to(device, non_blocking=True)
        if device.type == "cuda":
            with torch.amp.autocast(device_type="cuda"):
                logits_hf = model(x_hf)
        else:
            logits_hf = model(x_hf)
        probs_hf = torch.softmax(logits_hf, dim=1).cpu().numpy().squeeze()
        probs = (probs + probs_hf) / 2.0

    idx = int(np.argmax(probs))
    return {
        "label": class_names[idx],
        "confidence": float(probs[idx]),
        "probs": {k: float(v) for k, v in zip(class_names, probs)}
    }
