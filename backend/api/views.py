# api/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from PIL import Image
import io

from .inference import predict_image
from .model_loader import get_model_and_meta
from .llm import explain_prediction

class LabelsView(APIView):
    def get(self, request):
        _, class_names, _, _ = get_model_and_meta()
        return Response({"labels": class_names})

class AnalyzeView(APIView):
    def post(self, request):
        if "image" not in request.FILES:
            return Response({"detail": "Harap unggah field 'image'."}, status=400)

        user_prompt = request.data.get("prompt", "")
        img_file = request.FILES["image"]

        # Validasi sederhana
        if img_file.size > 5 * 1024 * 1024:
            return Response({"detail": "Ukuran file > 5MB."}, status=400)

        try:
            img_bytes = img_file.read()
            pil = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        except Exception:
            return Response({"detail": "Gagal membaca gambar. Pastikan format valid (JPG/PNG)."}, status=400)

        # Prediksi
        pred = predict_image(pil, tta=True)
        label, conf, probs = pred["label"], pred["confidence"], pred["probs"]

        # Penjelasan LLM
        explanation = explain_prediction(label, conf, probs, user_prompt)

        return Response({
            "prediction": label,
            "confidence": conf,
            "probs": probs,
            "explanation_md": explanation  # markdown siap render di frontend
        }, status=status.HTTP_200_OK)
