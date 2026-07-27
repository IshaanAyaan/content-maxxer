"""Small deterministic JSON and path helpers."""

import dataclasses
import enum
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict


def jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {field.name: jsonable(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable(value), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def digest_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "job"


def portable(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()
