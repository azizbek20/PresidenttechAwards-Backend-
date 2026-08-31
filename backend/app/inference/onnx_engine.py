from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort

from app.inference.engine import ModelUnavailable, Prediction
from app.inference.preprocess import to_model_input
from app.inference.torch_engine import NUM_CLASSES

logger = logging.getLogger("eyedetect.onnx_engine")


class OnnxEngine:
    """Real DR classifier using ONNX Runtime for faster CPU inference."""

    def __init__(self, settings: Any) -> None:
        self.model_loaded = False

        model_dir = Path(settings.eye_model_dir)
        self._model_version = str(settings.eye_model_version)
        self._input_size = int(getattr(settings, "engine_input_size", 224))
        
        # O'quvchi model.onnx yoki model_quant.onnx bo'lishi mumkin
        quant_model_path = model_dir / "model_quant.onnx"
        base_model_path = model_dir / "model.onnx"
        
        model_path = quant_model_path if quant_model_path.is_file() else base_model_path
        
        if not model_path.is_file():
            msg = f"no ONNX model artifact found at {model_path} (run export_onnx.py first)"
            raise ModelUnavailable(msg)
            
        logger.info(f"Loading ONNX model from {model_path}...")
        
        # CPU uchun execution providers va Optimizatsiya sozlamalari
        providers = ["CPUExecutionProvider"]
        sess_options = ort.SessionOptions()
        # Maksimal tezlik uchun hisoblash graflarini optimallashtirish (ORT_ENABLE_ALL)
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        # Celery kabi workerlarda CPU resurslarini talashmaslik uchun threadlar sonini cheklash
        sess_options.intra_op_num_threads = 2
        
        try:
            self.session = ort.InferenceSession(
                str(model_path), 
                sess_options=sess_options, 
                providers=providers
            )
            self.input_name = self.session.get_inputs()[0].name
            self.model_loaded = True
            logger.info(
                "onnx engine ready: version=%s artifact=%s",
                self._model_version,
                model_path,
            )
        except Exception as e:
            raise ModelUnavailable(f"Failed to load ONNX model: {e}")

    @property
    def device(self) -> str:
        return "cpu"

    @property
    def model_version(self) -> str:
        return self._model_version

    def _as_model_input(self, img: np.ndarray) -> np.ndarray:
        arr = np.asarray(img)
        is_chw_float = (
            arr.ndim == 3
            and arr.shape[0] == 3
            and np.issubdtype(arr.dtype, np.floating)
        )
        if is_chw_float:
            return np.ascontiguousarray(arr, dtype=np.float32)
        return to_model_input(arr, self._input_size)

    def predict(self, img: np.ndarray) -> Prediction:
        if not self.model_loaded:
            raise ModelUnavailable("onnx engine has no loaded model")

        # 1x3x224x224 massiv yaratamiz
        batch = np.expand_dims(self._as_model_input(img), axis=0).astype(np.float32)

        # Modelni ishga tushirish
        logits = self.session.run(None, {self.input_name: batch})[0][0]
        
        # Softmax hisoblash (numpy yordamida)
        exp_logits = np.exp(logits - np.max(logits))
        probs = exp_logits / exp_logits.sum()

        if probs.shape[0] != NUM_CLASSES:
            msg = f"model returned {probs.shape[0]} logits, expected {NUM_CLASSES}"
            raise ModelUnavailable(msg)

        return Prediction(
            grade=int(np.argmax(probs)),
            probs=[float(p) for p in probs],
            model_version=self._model_version,
        )
