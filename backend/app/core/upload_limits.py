"""Raise Starlette's 1 MB multipart cap so product PNG uploads are not rejected as 413."""

from __future__ import annotations

MAX_UPLOAD_PART_BYTES = 32 * 1024 * 1024

_installed = False


def install() -> None:
    global _installed
    if _installed:
        return
    from starlette.formparsers import MultiPartParser
    from starlette.requests import Request

    MultiPartParser.max_part_size = MAX_UPLOAD_PART_BYTES
    original_form = Request.form

    def form(
        self,
        *,
        max_files: int | float = 1000,
        max_fields: int | float = 1000,
        max_part_size: int = MAX_UPLOAD_PART_BYTES,
    ):
        return original_form(
            self,
            max_files=max_files,
            max_fields=max_fields,
            max_part_size=max_part_size,
        )

    Request.form = form  # type: ignore[method-assign]
    _installed = True


install()
