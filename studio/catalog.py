"""Read explicitly allowlisted, hash-bound packages without granting approval."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath

from pydantic import AwareDatetime, Field

from lib.master_story import validate_package
from studio.models import CanonicalReference, StrictModel


class CatalogEntry(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    title: str = Field(min_length=1, max_length=120)
    path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved_by: str = Field(min_length=1)
    approved_at: AwareDatetime


class PackageCatalog(StrictModel):
    schema_version: str = Field(pattern=r"^1\.0$")
    packages: list[CatalogEntry]


class ApprovedPackages:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root.resolve()
        self.path = self.repo_root / "studio/approved_packages.json"

    def _read_entry(self, entry: CatalogEntry) -> CanonicalReference:
        parts = PurePosixPath(entry.path).parts
        if ("\\" in entry.path or ":" in entry.path or ".." in parts
                or parts[:2] != ("examples", "master-story") or not entry.path.endswith(".json")):
            raise ValueError("Canonical package path is outside the approved package directory.")
        base = (self.repo_root / "examples/master-story").resolve()
        path = (self.repo_root / entry.path).resolve()
        if not path.is_relative_to(base) or not base.is_relative_to(self.repo_root):
            raise ValueError("Canonical package path escapes the repository.")
        if path.stat().st_size > 2_000_000:
            raise ValueError("Canonical package is too large.")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry.sha256:
            raise ValueError("Canonical package changed after catalog approval.")
        package = json.loads(raw.decode("utf-8"))
        validate_package(package)
        return CanonicalReference(catalog_id=entry.id, package_id=package["package_id"],
                                  package_version=package["package_version"], path=entry.path,
                                  sha256=entry.sha256, approved_by=entry.approved_by,
                                  approved_at=entry.approved_at)

    def available(self) -> tuple[list[dict], list[str]]:
        if not self.path.is_file():
            return [], []
        try:
            catalog = PackageCatalog.model_validate_json(self.path.read_bytes())
            if len({e.id for e in catalog.packages}) != len(catalog.packages):
                raise ValueError("Duplicate catalog IDs.")
        except (ValueError, OSError):
            return [], ["Canonical catalog is invalid; no packages can be selected."]
        available, warnings = [], []
        for entry in catalog.packages:
            try:
                ref = self._read_entry(entry)
                available.append({"id": entry.id, "title": entry.title,
                                  "reference": ref.model_dump(mode="json")})
            except (ValueError, OSError, KeyError):
                warnings.append(f"Package {entry.id} is unavailable or changed since approval.")
        return available, warnings

    def select(self, catalog_id: str) -> tuple[str, CanonicalReference]:
        packages, _ = self.available()
        entry = next((p for p in packages if p["id"] == catalog_id), None)
        if entry is None:
            raise ValueError("Select an available approved canonical package.")
        return entry["title"], CanonicalReference.model_validate(entry["reference"])
