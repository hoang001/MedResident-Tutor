"""Optional local CPU semantic encoder. No remote inference, no generative calls."""

import hashlib
import json
import threading
from pathlib import Path


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


class LocalSemanticEncoder:
    def __init__(self, path):
        import torch
        from transformers import AutoModel, AutoTokenizer

        self.path = Path(path)
        self.manifest = json.loads((self.path / "manifest.json").read_text(encoding="utf-8"))
        for name, expected in self.manifest["sha256"].items():
            if sha256_file(self.path / name) != expected:
                raise ValueError("RETRIEVAL_ENCODER_HASH_MISMATCH")
        self.torch = torch
        torch.set_num_threads(4)
        self.tokenizer = AutoTokenizer.from_pretrained(self.path, local_files_only=True)
        self.model = AutoModel.from_pretrained(self.path, local_files_only=True).to("cpu").eval()
        self.lock = threading.Lock()
        self.identity = {
            "model": self.manifest["model"],
            "revision": self.manifest["revision"],
            "device": "cpu",
            "dimensions": self.model.config.hidden_size,
            "pooling": "masked mean; L2; full-chunk mean of overlapping token-window vectors",
            "window_tokens": 480,
            "overlap_tokens": 64,
        }

    def encode(self, texts, *, query=False, progress=None):
        torch = self.torch
        import numpy as np

        windows, owners = [], []
        prefix = "query: " if query else "passage: "
        for index, text in enumerate(texts):
            tokens = self.tokenizer.encode(prefix + text, add_special_tokens=False)
            if query and len(tokens) > 480:
                raise ValueError("RETRIEVAL_QUERY_TOKEN_LIMIT")
            for start in range(0, len(tokens), 416):
                windows.append(
                    self.tokenizer.build_inputs_with_special_tokens(tokens[start : start + 480])
                )
                owners.append(index)
                if start + 480 >= len(tokens):
                    break
        sums = np.zeros((len(texts), self.identity["dimensions"]), dtype=np.float32)
        counts = np.zeros(len(texts), dtype=np.int32)
        with self.lock, torch.inference_mode():
            for start in range(0, len(windows), 12):
                batch = self.tokenizer.pad(
                    {"input_ids": windows[start : start + 12]}, padding=True, return_tensors="pt"
                )
                assert batch["input_ids"].shape[1] <= 512
                hidden = self.model(**batch).last_hidden_state
                mask = batch["attention_mask"].unsqueeze(-1)
                vectors = (hidden * mask).sum(1) / mask.sum(1)
                vectors = torch.nn.functional.normalize(vectors, p=2, dim=1).cpu().numpy()
                for offset, vector in enumerate(vectors):
                    owner = owners[start + offset]
                    sums[owner] += vector
                    counts[owner] += 1
                if progress:
                    progress(min(start + 12, len(windows)), len(windows))
        sums /= counts[:, None]
        sums /= np.maximum(np.linalg.norm(sums, axis=1, keepdims=True), 1e-12)
        return sums
