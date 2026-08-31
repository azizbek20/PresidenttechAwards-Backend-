import argparse
import logging
from pathlib import Path

import torch
import onnx
from onnxruntime.quantization import quantize_dynamic, QuantType

# app.config va app.inference import qilish orqali mavjud TorchEngine'dan foydalanamiz
import sys
sys.path.append(str(Path(__file__).parent.parent))

from app.config import Settings
from app.inference.torch_engine import TorchEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("export_onnx")


def export_model(model_dir: Path, output_path: Path, quantize: bool = True):
    logger.info(f"Loading TorchEngine from {model_dir}...")
    settings = Settings(EYE_MODEL_DIR=str(model_dir), EYE_DEVICE="cpu")
    
    try:
        engine = TorchEngine(settings)
    except Exception as e:
        logger.error(f"Failed to load torch model: {e}")
        return

    model = engine.model
    model.eval()

    # Create dummy input based on expected input size
    # Typically 224x224 RGB image, so batch_size=1, channels=3, H=224, W=224
    input_size = getattr(settings, "engine_input_size", 224)
    dummy_input = torch.randn(1, 3, input_size, input_size, dtype=torch.float32)

    logger.info(f"Exporting model to ONNX format at {output_path}...")
    torch.onnx.export(
        model,
        dummy_input,
        str(output_path),
        export_params=True,
        opset_version=14,
        do_constant_folding=True,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={
            "input": {0: "batch_size"},
            "output": {0: "batch_size"}
        }
    )
    logger.info("ONNX export completed.")

    if quantize:
        quantized_path = output_path.with_name(f"{output_path.stem}_quant.onnx")
        logger.info(f"Quantizing model to INT8 at {quantized_path}...")
        quantize_dynamic(
            str(output_path),
            str(quantized_path),
            weight_type=QuantType.QUInt8
        )
        logger.info("ONNX quantization completed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export PyTorch model to ONNX")
    parser.add_argument("--model-dir", type=str, default="./models", help="Directory containing model.pt")
    parser.add_argument("--output", type=str, default="./models/model.onnx", help="Output ONNX file path")
    parser.add_argument("--no-quantize", action="store_true", help="Disable dynamic INT8 quantization")
    
    args = parser.parse_args()
    
    export_model(Path(args.model_dir), Path(args.output), not args.no_quantize)
