from datetime import datetime
from pathlib import Path


def get_timestamped_dirs(data_dir: Path, limit: int | None = None) -> list[Path]:
    if not data_dir.exists():
        return []

    data_dirs = [
        path
        for path in data_dir.iterdir()
        if path.is_dir() and path.name.replace("_", "").isdigit()
    ]
    sorted_dirs = sorted(
        data_dirs,
        key=lambda path: datetime.strptime(path.name, "%Y%m%d_%H%M%S"),
        reverse=True,
    )
    return sorted_dirs[:limit] if limit else sorted_dirs
