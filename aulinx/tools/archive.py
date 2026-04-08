"""Archive tools — compress and extract files."""

import shutil
from pathlib import Path

from aulinx.tools.base import Tier, Tool


async def archive_create(path: str, output: str = "", format: str = "zip") -> dict:
    """Create an archive from a file or directory.

    Formats: zip, tar, tar.gz, tar.bz2
    """
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return {"error": f"Path not found: {path}"}

    if not output:
        output = str(p) + (".zip" if format == "zip" else f".{format}")

    try:
        if format == "zip":
            if p.is_dir():
                shutil.make_archive(str(Path(output).with_suffix("")), "zip", str(p.parent), p.name)
            else:
                import zipfile
                with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
                    zf.write(str(p), p.name)
        elif format in ("tar", "tar.gz", "tar.bz2"):
            mode_map = {"tar": "w", "tar.gz": "w:gz", "tar.bz2": "w:bz2"}
            import tarfile
            with tarfile.open(output, mode_map[format]) as tf:
                tf.add(str(p), p.name)
        else:
            return {"error": f"Unsupported format: {format}. Use zip, tar, tar.gz, tar.bz2"}

        out_path = Path(output)
        if out_path.exists():
            return {"created": True, "path": str(out_path), "size_bytes": out_path.stat().st_size, "format": format}
        return {"error": "Archive creation failed"}

    except Exception as e:
        return {"error": str(e)}


async def archive_extract(path: str, destination: str = "") -> dict:
    """Extract an archive (zip, tar, tar.gz, tar.bz2)."""
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        return {"error": f"File not found: {path}"}

    if not destination:
        destination = str(p.parent / p.stem)

    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)

    try:
        name = p.name.lower()
        if name.endswith(".zip"):
            import zipfile
            with zipfile.ZipFile(str(p)) as zf:
                zf.extractall(str(dest))
        elif name.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2")):
            import tarfile
            with tarfile.open(str(p)) as tf:
                tf.extractall(str(dest))
        else:
            return {"error": f"Unsupported format: {p.suffix}"}

        files = list(dest.rglob("*"))
        return {"extracted": True, "destination": str(dest), "files": len(files)}

    except Exception as e:
        return {"error": str(e)}


async def archive_list(path: str) -> list[str]:
    """List contents of an archive without extracting."""
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        return [f"File not found: {path}"]

    try:
        name = p.name.lower()
        if name.endswith(".zip"):
            import zipfile
            with zipfile.ZipFile(str(p)) as zf:
                return zf.namelist()[:50]
        elif name.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2")):
            import tarfile
            with tarfile.open(str(p)) as tf:
                return tf.getnames()[:50]
        return [f"Unsupported format: {p.suffix}"]
    except Exception as e:
        return [f"Error: {e}"]


TOOLS = [
    Tool(
        name="archive_create",
        description="Create a zip/tar archive from a file or directory",
        fn=archive_create,
        parameters={
            "path": "string (file or directory to archive)",
            "output": "string (optional output path, auto-generated if empty)",
            "format": "zip|tar|tar.gz|tar.bz2 (default: zip)",
        },
        tier=Tier.MUTATE,
    ),
    Tool(
        name="archive_extract",
        description="Extract a zip/tar archive",
        fn=archive_extract,
        parameters={
            "path": "string (archive file path)",
            "destination": "string (optional extract destination)",
        },
        tier=Tier.MUTATE,
    ),
    Tool(
        name="archive_list",
        description="List contents of an archive without extracting",
        fn=archive_list,
        parameters={"path": "string (archive file path)"},
        tier=Tier.OBSERVE,
    ),
]
