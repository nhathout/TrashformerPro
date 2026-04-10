from __future__ import annotations

import base64
import hashlib
import io
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Generator, List

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = Path(__file__).resolve().parent
DB_DIR = BACKEND_DIR / "data" / "db"
DB_PATH = DB_DIR / "history.db"
CLASSES = ["plastic", "paper_cardboard", "metal_glass", "trash_other"]

def _get_db():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            category TEXT,
            confidence REAL,
            inference_time_ms REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    return conn


def _resolve_checkpoint_path() -> Path | None:
    env_value = os.getenv("TRASHFORMER_CHECKPOINT")
    if env_value:
        checkpoint = Path(env_value).expanduser()
        if not checkpoint.is_absolute():
            checkpoint = REPO_ROOT / checkpoint
        if checkpoint.exists():
            return checkpoint

    default_checkpoint = REPO_ROOT / "runtime" / "models" / "best.pt"
    if default_checkpoint.exists():
        return default_checkpoint

    run_checkpoints = sorted(
        (REPO_ROOT / "training" / "runs").glob("**/best.pt"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return run_checkpoints[0] if run_checkpoints else None


def _classify_with_checkpoint(image: Image.Image, checkpoint_path: Path) -> Dict[str, Any]:
    import torch

    from training.modeling import build_eval_transform, build_model

    device = torch.device("cpu")
    checkpoint = torch.load(checkpoint_path, map_location=device)
    class_names = checkpoint["class_names"]
    model_name = checkpoint["model_name"]
    img_size = int(checkpoint.get("img_size", 224))

    model = build_model(model_name, len(class_names), pretrained=False)
    model.load_state_dict(checkpoint["model_state"])
    model.to(device)
    model.eval()

    transform = build_eval_transform(img_size)
    input_tensor = transform(image).unsqueeze(0).to(device)

    with torch.no_grad():
        logits = model(input_tensor)
        probabilities = torch.softmax(logits, dim=1)[0].cpu()

    top_index = int(probabilities.argmax().item())
    confidence = float(probabilities[top_index].item())
    return {
        "category": class_names[top_index],
        "confidence": round(confidence, 4),
        "model_source": str(checkpoint_path.relative_to(REPO_ROOT)),
    }


def _classify_with_mock(image_data: bytes) -> Dict[str, Any]:
    img_hash = int(hashlib.md5(image_data).hexdigest(), 16)
    category = CLASSES[img_hash % len(CLASSES)]
    confidence = 0.85 + ((img_hash % 1400) / 10000)
    return {
        "category": category,
        "confidence": round(min(confidence, 0.99), 4),
        "model_source": "mock",
    }


def _classify_image(image: Image.Image, image_data: bytes) -> Dict[str, Any]:
    checkpoint_path = _resolve_checkpoint_path()
    if checkpoint_path is None:
        return _classify_with_mock(image_data)

    try:
        return _classify_with_checkpoint(image, checkpoint_path)
    except Exception as exc:
        print(f"[BACKEND_WARN] Falling back to mock inference: {exc}")
        return _classify_with_mock(image_data)

def classify_image_streaming(**args) -> Generator:
    image_b64 = args.get("image_b64", "")
    filename = args.get("filename", "unknown.jpg")
    
    print(f"[BACKEND_START] classify_image_streaming for {filename}")
    
    try:
        yield {"status": "processing", "progress": 10, "message": "Decoding image..."}
        
        # Decode image
        header, encoded = image_b64.split(",", 1) if "," in image_b64 else (None, image_b64)
        image_data = base64.b64decode(encoded)
        image = Image.open(io.BytesIO(image_data)).convert("RGB")

        yield {"status": "processing", "progress": 30, "message": "Preprocessing image..."}

        start_time = time.time()

        checkpoint_path = _resolve_checkpoint_path()
        if checkpoint_path is not None:
            yield {"status": "processing", "progress": 60, "message": "Running checkpoint inference..."}
        else:
            yield {"status": "processing", "progress": 60, "message": "Checkpoint missing, using demo inference..."}

        prediction = _classify_image(image, image_data)
        if prediction["model_source"] == "mock":
            time.sleep(0.35)

        inference_time_ms = (time.time() - start_time) * 1000

        result = {
            "category": prediction["category"],
            "confidence": prediction["confidence"],
            "inference_time_ms": round(inference_time_ms, 2),
            "model_source": prediction["model_source"],
        }

        yield {"status": "processing", "progress": 80, "message": "Logging to database..."}

        # Log to DB
        conn = _get_db()
        try:
            conn.execute("""
                INSERT INTO predictions (filename, category, confidence, inference_time_ms)
                VALUES (?, ?, ?, ?)
            """, (filename, result["category"], result["confidence"], inference_time_ms))
            conn.commit()
        finally:
            conn.close()

        print(f"[BACKEND_SUCCESS] classify_image_streaming complete: {result['category']}")
        yield {"status": "success", "progress": 100, "result": result}

    except Exception as e:
        print(f"[BACKEND_ERROR] classify_image_streaming failed: {str(e)}")
        yield {"status": "error", "progress": 0, "error": str(e)}

def get_history(limit: int = 50) -> List[Dict[str, Any]]:
    print(f"[BACKEND_START] get_history with limit={limit}")
    conn = _get_db()
    try:
        rows = conn.execute("""
            SELECT * FROM predictions ORDER BY created_at DESC LIMIT ?
        """, (limit,)).fetchall()
        result = [dict(row) for row in rows]
        print(f"[BACKEND_SUCCESS] get_history returned {len(result)} records")
        return result
    except Exception as e:
        print(f"[BACKEND_ERROR] get_history failed: {str(e)}")
        raise
    finally:
        conn.close()

def get_stats() -> Dict[str, Any]:
    print("[BACKEND_START] get_stats")
    conn = _get_db()
    try:
        total_count = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
        
        category_rows = conn.execute("""
            SELECT category, COUNT(*) as count FROM predictions GROUP BY category
        """).fetchall()
        
        category_counts = {c: 0 for c in CLASSES}
        for row in category_rows:
            category_counts[row['category']] = row['count']
            
        avg_inference_time = conn.execute("SELECT AVG(inference_time_ms) FROM predictions").fetchone()[0] or 0.0
        
        result = {
            "total_count": total_count,
            "category_counts": category_counts,
            "avg_inference_time": round(avg_inference_time, 2)
        }
        print(f"[BACKEND_SUCCESS] get_stats: total={total_count}")
        return result
    except Exception as e:
        print(f"[BACKEND_ERROR] get_stats failed: {str(e)}")
        raise
    finally:
        conn.close()

def clear_history() -> Dict[str, bool]:
    print("[BACKEND_START] clear_history")
    conn = _get_db()
    try:
        conn.execute("DELETE FROM predictions")
        conn.commit()
        print("[BACKEND_SUCCESS] history cleared")
        return {"success": True}
    except Exception as e:
        print(f"[BACKEND_ERROR] clear_history failed: {str(e)}")
        raise
    finally:
        conn.close()
