"""Small CUDA/NF4 kernel check only. Does not load either language model."""

import gc
import importlib.metadata
import platform
import os

from .common import REPORT, system_snapshot, write


def main():
    report = {
        "pid": os.getpid(),
        "before": system_snapshot(),
        "python": platform.python_version(),
        "model_inference": False,
    }
    torch = None
    try:
        import torch
        import bitsandbytes as bnb
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
        )  # verify imports, no loading
        from peft import PeftModel

        assert all((AutoModelForCausalLM, AutoTokenizer, PeftModel))
        report["packages"] = {
            p: importlib.metadata.version(p)
            for p in (
                "torch",
                "transformers",
                "peft",
                "accelerate",
                "bitsandbytes",
                "huggingface-hub",
            )
        }
        report["cuda"] = {
            "available": torch.cuda.is_available(),
            "build": torch.version.cuda,
            "device": torch.cuda.get_device_name(0),
            "capability": torch.cuda.get_device_capability(0),
            "compiled_architectures": torch.cuda.get_arch_list(),
        }
        assert torch.cuda.is_available(), "CUDA unavailable; no CPU fallback"
        with torch.inference_mode():
            data = torch.randn(128, 128, device="cuda", dtype=torch.float16)
            result = data @ data.T
            assert bool(torch.isfinite(result).all())
            quant, state = bnb.functional.quantize_4bit(
                data, quant_type="nf4", compress_statistics=True
            )
            restored = bnb.functional.dequantize_4bit(quant, state)
            assert restored.shape == data.shape and bool(torch.isfinite(restored).all())
            layer = bnb.nn.Linear4bit(
                128,
                64,
                bias=False,
                compute_dtype=torch.float16,
                compress_statistics=True,
                quant_type="nf4",
            ).to("cuda")
            output = layer(data[:1])
            assert output.shape == (1, 64) and bool(torch.isfinite(output).all())
            torch.cuda.synchronize()
            report["cuda_matmul_and_nf4_double_quant"] = "passed"
            report["peak_allocated_bytes"] = torch.cuda.max_memory_allocated()
            del data, result, quant, state, restored, layer, output
        report["status"] = "runtime_probe_passed_not_model_test"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        gc.collect()
        if torch is not None:
            torch.cuda.empty_cache()
        write(REPORT / "runtime-probe.json", report)
    print(report["status"], report["packages"], report["cuda"])


if __name__ == "__main__":
    main()
