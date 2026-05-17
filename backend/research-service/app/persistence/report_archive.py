import json
from pathlib import Path

from app.contracts.archive import ReportArchiveArtifact, safe_archive_file_name


class JsonReportArchiveWriter:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def write(self, artifact: ReportArchiveArtifact) -> Path:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        path = self.base_dir / safe_archive_file_name(artifact.run_id)
        tmp_path = path.with_name(f"{path.name}.tmp")
        payload = artifact.model_dump(mode="json")
        tmp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(path)
        return path
