"""Source retrieval, normalization, and per-job cache management."""

import json
import mimetypes
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .io import digest_text, portable, read_json, slugify, write_json
from .models import SourceArtifact


class SourceError(RuntimeError):
    pass


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag in {"script", "style", "svg", "noscript"}:
            self.ignored_depth += 1
        elif self.ignored_depth == 0 and tag in {"p", "div", "section", "article", "li", "h1", "h2", "h3", "h4", "br"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "svg", "noscript"} and self.ignored_depth:
            self.ignored_depth -= 1
        elif self.ignored_depth == 0 and tag in {"p", "div", "section", "article", "li"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.ignored_depth == 0:
            self.parts.append(data)


def normalize_text(raw: str, content_type: str = "text/plain") -> str:
    text = raw
    if "html" in content_type.lower() or "<html" in raw[:1000].lower():
        parser = _TextExtractor()
        parser.feed(raw)
        text = " ".join(parser.parts)
    lines: List[str] = []
    blank = False
    for source_line in text.replace("\r", "\n").split("\n"):
        line = " ".join(source_line.split())
        if line:
            lines.append(line)
            blank = False
        elif lines and not blank:
            lines.append("")
            blank = True
    return "\n".join(lines).strip() + "\n"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _artifact_from_dict(data: Dict[str, object]) -> SourceArtifact:
    return SourceArtifact(**{key: data[key] for key in SourceArtifact.__dataclass_fields__})


def load_source_artifacts(job_dir: Path) -> List[SourceArtifact]:
    index = job_dir / "sources" / "index.json"
    if not index.exists():
        return []
    payload = read_json(index)
    return [_artifact_from_dict(item) for item in payload.get("sources", [])]


class SourceCache:
    def __init__(self, job_dir: Path, snapshot_date: Optional[str] = None) -> None:
        self.job_dir = job_dir
        self.root = job_dir / "sources"
        self.root.mkdir(parents=True, exist_ok=True)
        self.snapshot_date = snapshot_date
        self.existing = {item.origin: item for item in load_source_artifacts(job_dir)}

    def _write(
        self,
        *,
        origin: str,
        label: str,
        source_type: str,
        raw: str,
        content_type: str,
        suffix: str,
        retrieval: Dict[str, object],
    ) -> SourceArtifact:
        normalized = normalize_text(raw, content_type)
        digest = digest_text(normalized)
        parsed = urllib.parse.urlparse(origin)
        stem_hint = parsed.netloc + parsed.path if parsed.scheme else Path(origin).stem
        stem = slugify(stem_hint)[:72] or "source"
        source_id = "src_" + digest[:10]
        base = self.root / f"{stem}_{digest[:8]}"
        snapshot_path = base.with_name(base.name + ".snapshot" + suffix)
        normalized_path = base.with_name(base.name + ".normalized.txt")
        metadata_path = base.with_name(base.name + ".metadata.json")
        snapshot_path.write_text(raw, encoding="utf-8")
        normalized_path.write_text(normalized, encoding="utf-8")
        retrieved_at = self.snapshot_date or _utc_now()
        artifact = SourceArtifact(
            id=source_id,
            label=label,
            origin=origin,
            source_type=source_type,
            retrieved_at=retrieved_at,
            digest=digest,
            normalized_path=portable(normalized_path, self.job_dir),
            snapshot_path=portable(snapshot_path, self.job_dir),
            metadata_path=portable(metadata_path, self.job_dir),
        )
        metadata = {
            "schema_version": "1.0",
            "artifact": artifact,
            "content_type": content_type,
            "bytes": len(raw.encode("utf-8")),
            "normalized_bytes": len(normalized.encode("utf-8")),
            "retrieval": retrieval,
        }
        write_json(metadata_path, metadata)
        self.existing[origin] = artifact
        return artifact

    def cache_url(self, url: str, offline: bool = False, label: Optional[str] = None) -> SourceArtifact:
        if url in self.existing:
            return self.existing[url]
        if offline:
            raise SourceError(f"offline cache miss: {url}")
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "contentmaxxer/0.2 source cache (+https://openai.com)",
                "Accept": "text/html,text/plain,application/json;q=0.9,*/*;q=0.5",
            },
        )
        urllib_failure: Optional[Exception] = None
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
                raw = payload.decode(charset, errors="replace")
                content_type = response.headers.get_content_type() or "text/html"
                final_url = response.geturl()
                status = getattr(response, "status", 200)
                headers = {key.lower(): value for key, value in response.headers.items()}
        except (urllib.error.URLError, TimeoutError) as exc:
            urllib_failure = exc
            curl = shutil.which("curl")
            if curl is None:
                raise SourceError(f"could not retrieve {url}: {exc}") from exc
            with tempfile.TemporaryDirectory(prefix="contentmaxxer-source-") as temp_dir:
                body_path = Path(temp_dir) / "body"
                headers_path = Path(temp_dir) / "headers"
                command = [
                    curl,
                    "-L",
                    "--fail",
                    "--silent",
                    "--show-error",
                    "--max-time",
                    "30",
                    "-A",
                    "Mozilla/5.0 (compatible; contentmaxxer/0.2; source snapshot)",
                    "-D",
                    str(headers_path),
                    "-o",
                    str(body_path),
                    "-w",
                    "%{url_effective}\n%{http_code}\n%{content_type}",
                    url,
                ]
                completed = subprocess.run(command, capture_output=True, text=True)
                if completed.returncode != 0 or not body_path.exists():
                    detail = (completed.stderr or completed.stdout).strip()
                    raise SourceError(f"could not retrieve {url} with urllib ({exc}) or curl ({detail})") from exc
                result_lines = completed.stdout.splitlines()
                final_url = result_lines[0] if result_lines else url
                status = int(result_lines[1]) if len(result_lines) > 1 and result_lines[1].isdigit() else 200
                content_type = result_lines[2].split(";", 1)[0] if len(result_lines) > 2 else "text/html"
                payload = body_path.read_bytes()
                raw = payload.decode("utf-8", errors="replace")
                header_lines = headers_path.read_text(encoding="utf-8", errors="replace").splitlines()
                headers = {}
                for header_line in header_lines:
                    if ":" in header_line:
                        key, value = header_line.split(":", 1)
                        headers[key.strip().lower()] = value.strip()
                headers["x-contentmaxxer-transport"] = "curl-fallback"
        suffix = ".html" if "html" in content_type else ".txt"
        host = urllib.parse.urlparse(url).netloc.replace("www.", "")
        return self._write(
            origin=url,
            label=label or host or url,
            source_type="url",
            raw=raw,
            content_type=content_type,
            suffix=suffix,
            retrieval={"requested_url": url, "final_url": final_url, "status": status, "headers": headers},
        )

    def cache_file(self, source_path: Path, label: Optional[str] = None) -> SourceArtifact:
        source_path = source_path.expanduser().resolve()
        origin = source_path.as_posix()
        if origin in self.existing:
            return self.existing[origin]
        if not source_path.is_file():
            raise SourceError(f"source file does not exist: {source_path}")
        raw = source_path.read_text(encoding="utf-8", errors="replace")
        content_type = mimetypes.guess_type(source_path.name)[0] or "text/plain"
        suffix = source_path.suffix if source_path.suffix else ".txt"
        return self._write(
            origin=origin,
            label=label or source_path.name,
            source_type="file",
            raw=raw,
            content_type=content_type,
            suffix=suffix,
            retrieval={"source_path": origin, "copied": True, "modified_at": source_path.stat().st_mtime},
        )

    def cache_text(self, origin: str, label: str, text: str, source_type: str = "url") -> SourceArtifact:
        """Cache a packaged snapshot when a remote source cannot be reached."""
        if origin in self.existing:
            return self.existing[origin]
        return self._write(
            origin=origin,
            label=label,
            source_type=source_type,
            raw=text,
            content_type="text/plain",
            suffix=".txt",
            retrieval={"packaged_snapshot": True, "network_retrieval": False},
        )

    def write_index(self, artifacts: Iterable[SourceArtifact]) -> Path:
        ordered = sorted({item.origin: item for item in artifacts}.values(), key=lambda item: item.origin)
        path = self.root / "index.json"
        write_json(path, {"schema_version": "1.0", "snapshot_date": self.snapshot_date, "sources": ordered})
        return path


def research_sources(
    job_dir: Path,
    source_urls: Iterable[str] = (),
    source_files: Iterable[Path] = (),
    offline: bool = False,
    snapshot_date: Optional[str] = None,
) -> List[SourceArtifact]:
    cache = SourceCache(job_dir, snapshot_date=snapshot_date)
    artifacts: List[SourceArtifact] = []
    urls = list(source_urls)
    files = list(source_files)
    if not urls and not files:
        artifacts = load_source_artifacts(job_dir)
    else:
        for url in urls:
            artifacts.append(cache.cache_url(url, offline=offline))
            cache.write_index(artifacts)
        for source_file in files:
            artifacts.append(cache.cache_file(Path(source_file)))
            cache.write_index(artifacts)
    cache.write_index(artifacts)
    return artifacts


def read_normalized_source(job_dir: Path, artifact: SourceArtifact) -> str:
    return (job_dir / artifact.normalized_path).read_text(encoding="utf-8")
