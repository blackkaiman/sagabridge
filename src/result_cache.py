# src/result_cache.py
"""
Cache de rezultate pe disc pentru pipeline-ul de extragere.

Scop: la o demonstratie/prezentare, facturile pot fi pre-procesate o singura
data (lent, cu Ollama), iar rezultatul se salveaza pe disc indexat dupa
continutul PDF-ului (hash SHA-256). La o re-incarcare a aceluiasi fisier,
rezultatul se serveste instant din cache, sarind peste pasul lent de LLM.

Cache-ul se invalideaza automat daca se schimba continutul fisierului
(alt hash) sau modelul folosit (inclus in cheie). Astfel, daca regenerezi o
factura cu alt model, NU primesti din greseala un rezultat vechi.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional, Union

_PathLike = Union[str, Path]


def file_sha256(path: _PathLike) -> str:
    """Hash SHA-256 al continutului fisierului — cheie stabila de cache."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def cache_key(path: _PathLike, model: Optional[str]) -> str:
    """Cheia de cache = hash continut + model (rezultate diferite per model)."""
    return f"{file_sha256(path)}__{model or 'default'}"


def _path_for(cache_dir: _PathLike, key: str) -> Path:
    return Path(cache_dir) / f"{key}.json"


def load(cache_dir: _PathLike, key: str) -> Optional[Dict[str, Any]]:
    """Returneaza payload-ul cache-uit, sau None daca lipseste / e corupt."""
    p = _path_for(cache_dir, key)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_any(cache_dir: _PathLike, file_hash: str) -> Optional[Dict[str, Any]]:
    """
    Returneaza primul rezultat cache-uit pentru acest CONTINUT de fisier,
    indiferent de model. Astfel, o factura procesata in Bulk (model default)
    este servita din cache si in modul Single (orice model), si invers.
    """
    d = Path(cache_dir)
    if not d.exists():
        return None
    for p in sorted(d.glob(f"{file_hash}__*.json")):
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return None


def save(cache_dir: _PathLike, key: str, payload: Dict[str, Any]) -> None:
    """
    Scrie payload-ul in cache, atomic (scrie in .tmp apoi rename), ca o
    intrerupere in timpul scrierii sa nu lase un fisier JSON corupt.
    """
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    target = _path_for(cache_dir, key)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(target)
