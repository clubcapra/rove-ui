"""Resolve bundled viewer imports even when the generated page lives in /tmp."""
from pathlib import Path


def local_viewer_imports(template: str) -> str:
    vendor = Path(__file__).resolve().parent / "html" / "vendor" / "three"
    return template.replace("__THREE_MODULE__", (vendor / "build/three.module.js").as_uri()).replace(
        "__THREE_ADDONS__", (vendor / "examples/jsm").as_uri() + "/"
    )
