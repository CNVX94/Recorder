"""Sintesis de notas: agrupa y limpia una nota diaria sin tocar nunca el original."""

from .parser import Entry, Note, parse_file, parse_text
from .transforms import (
    INTERVALS,
    DigestOptions,
    apply_all,
    bucket_start,
    drop_short,
    group_by_interval,
    merge_consecutive,
    strip_captures,
)
from .writer import (
    AVISO,
    DerivedSourceError,
    WouldOverwriteSourceError,
    build_digest,
    digest_path,
    is_digest,
    list_originals,
    render,
    unique_digest_path,
    write_digest,
)

__all__ = [
    "Entry",
    "Note",
    "parse_file",
    "parse_text",
    "INTERVALS",
    "DigestOptions",
    "apply_all",
    "bucket_start",
    "drop_short",
    "group_by_interval",
    "merge_consecutive",
    "strip_captures",
    "AVISO",
    "DerivedSourceError",
    "WouldOverwriteSourceError",
    "build_digest",
    "digest_path",
    "is_digest",
    "list_originals",
    "render",
    "unique_digest_path",
    "write_digest",
]
