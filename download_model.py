"""Script to download and save CrossEncoder reranker models locally for offline low-latency inference."""

import argparse
import os
from pathlib import Path
from sentence_transformers import CrossEncoder

DEFAULT_MODEL = os.getenv("RERANKER_MODEL_NAME", "cross-encoder/ms-marco-MiniLM-L-6-v2")
DEFAULT_TARGET_DIR = os.getenv(
    "RERANKER_MODEL_PATH",
    str(Path(__file__).parent / "models" / "ms-marco-MiniLM-L-6-v2"),
)


def download_model(model_name: str, target_dir: str, max_length: int = 256) -> str:
    print(f"Downloading reranker '{model_name}' to '{target_dir}' (max_length={max_length})...")
    os.makedirs(target_dir, exist_ok=True)
    model = CrossEncoder(model_name, max_length=max_length)
    model.save_pretrained(target_dir)
    print(f"Successfully saved reranker model to: {target_dir}")
    print("\nTo use this local model in your app, set in your .env:")
    print(f"RERANKER_MODEL_NAME={target_dir}")
    print(f"RERANKER_MAX_LENGTH={max_length}")
    print("RERANKER_LOCAL_FILES_ONLY=true")
    return target_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download CrossEncoder reranker models locally.")
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help="HuggingFace model repo id (e.g., cross-encoder/ms-marco-MiniLM-L-6-v2 or BAAI/bge-reranker-base)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=DEFAULT_TARGET_DIR,
        help="Local directory where the model will be stored",
    )
    parser.add_argument(
        "--max-length",
        type=int,
        default=256,
        help="Maximum sequence length for tokenization truncation",
    )

    args = parser.parse_args()
    download_model(args.model, args.output_dir, args.max_length)

