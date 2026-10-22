"""Strict input and saved-request contracts; no production orchestration."""

from __future__ import annotations

import hashlib
import re
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_CONTENT_CHARS = 200_000
MAX_CONTENT_BYTES = 1_000_000
PROJECT_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{0,63}$"
SHA256_PATTERN = r"^[a-f0-9]{64}$"
InputMode = Literal["topic", "story", "canonical"]
OutputFormat = Literal["short", "long"]


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def safe_project_id(value: str) -> str:
    if not re.fullmatch(PROJECT_ID_PATTERN, value):
        raise ValueError("Project ID must use 1–64 lowercase letters, digits or hyphens.")
    if value in {"con", "prn", "aux", "nul"} or re.fullmatch(r"(?:com|lpt)[0-9]", value):
        raise ValueError("Project ID is a reserved Windows name.")
    return value


def plain_text(value: str) -> str:
    if any((ord(c) < 32 and c not in "\r\n\t") or ord(c) == 127 for c in value):
        raise ValueError("Input contains unsupported control characters.")
    try:
        if len(value.encode("utf-8")) > MAX_CONTENT_BYTES:
            raise ValueError("Input exceeds the 1 MB UTF-8 limit.")
    except UnicodeEncodeError as exc:
        raise ValueError("Input must contain valid UTF-8 text.") from exc
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)


class NewProduction(StrictModel):
    project_id: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=120)
    input_mode: InputMode
    content: str | None = Field(default=None, max_length=MAX_CONTENT_CHARS)
    canonical_package_id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    source_filename: str | None = Field(default=None, max_length=160)
    formats: list[OutputFormat] = Field(min_length=1, max_length=2, json_schema_extra={"uniqueItems": True})
    style: Literal["stickman_horror_2d"] = "stickman_horror_2d"
    review_mode: Literal["human_required"] = "human_required"
    publishing_enabled: Literal[False] = False

    @field_validator("project_id")
    @classmethod
    def project_id_is_safe(cls, value):
        return safe_project_id(value) if value is not None else value

    @field_validator("title", "content")
    @classmethod
    def text_is_safe(cls, value):
        return plain_text(value) if value is not None else value

    @field_validator("title")
    @classmethod
    def nonempty_title(cls, value):
        if value is not None and (not value.strip() or "\n" in value or "\r" in value):
            raise ValueError("Title must be a nonempty single line.")
        return value

    @field_validator("source_filename")
    @classmethod
    def markdown_filename(cls, value):
        if value is not None:
            plain_text(value)
            if any(c in value for c in '/\\:<>"|?*') or not value.lower().endswith((".md", ".markdown")):
                raise ValueError("Upload a Markdown filename without a directory path.")
        return value

    @field_validator("formats")
    @classmethod
    def unique_formats(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Choose each output format only once.")
        return sorted(value, key=("short", "long").index)

    @field_validator("publishing_enabled", mode="before")
    @classmethod
    def publishing_is_disabled(cls, value):
        if value is not False:
            raise ValueError("Publishing is disabled in this milestone.")
        return value

    @model_validator(mode="after")
    def mode_specific_input(self):
        if self.input_mode == "canonical":
            if not self.canonical_package_id or self.content is not None or self.source_filename is not None:
                raise ValueError("Canonical mode requires a catalog ID and does not accept text or uploads.")
        elif self.canonical_package_id is not None or self.content is None or not self.content.strip():
            raise ValueError("Enter a topic or full story for the selected mode.")
        return self


class CanonicalReference(StrictModel):
    catalog_id: str
    package_id: str
    package_version: str
    path: str
    sha256: str = Field(pattern=SHA256_PATTERN)
    approved_by: str = Field(min_length=1)
    approved_at: AwareDatetime


class ProductionRequest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    title: str = Field(min_length=1, max_length=120)
    input_mode: InputMode
    content: str | None = Field(max_length=MAX_CONTENT_CHARS)
    content_sha256: str = Field(pattern=SHA256_PATTERN)
    input_file: Literal["input/topic.txt", "input/story.md", "input/canonical-reference.json"]
    source_filename: str | None = None
    formats: list[OutputFormat] = Field(min_length=1, max_length=2, json_schema_extra={"uniqueItems": True})
    style: Literal["stickman_horror_2d"] = "stickman_horror_2d"
    review_mode: Literal["human_required"] = "human_required"
    review_status: Literal["pending_human_review"] = "pending_human_review"
    publishing_enabled: Literal[False] = False
    status: Literal["production_not_started"] = "production_not_started"
    input_readiness: Literal["unresearched_topic", "unreviewed_story", "canonical_reference"]
    created_at: AwareDatetime
    canonical_package: CanonicalReference | None = None

    @model_validator(mode="after")
    def consistent_saved_input(self):
        safe_project_id(self.project_id)
        NewProduction(project_id=self.project_id, title=self.title, input_mode=self.input_mode,
                      content=self.content, formats=self.formats, source_filename=self.source_filename,
                      canonical_package_id=self.canonical_package.catalog_id if self.canonical_package else None,
                      style=self.style, review_mode=self.review_mode, publishing_enabled=self.publishing_enabled)
        expected = {"topic": ("input/topic.txt", "unresearched_topic"),
                    "story": ("input/story.md", "unreviewed_story"),
                    "canonical": ("input/canonical-reference.json", "canonical_reference")}
        if (self.input_file, self.input_readiness) != expected[self.input_mode]:
            raise ValueError("Saved input mode and readiness do not match.")
        sha = self.canonical_package.sha256 if self.canonical_package else content_hash(self.content)
        if sha != self.content_sha256:
            raise ValueError("Original input hash does not match.")
        return self
