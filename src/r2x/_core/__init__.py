"""Internal shared infrastructure for R2X translations."""

from .base import TranslatorProtocol
from .dry_run import create_empty_preview
from .errors import (
    find_closest_match,
    format_mapping_error,
    format_translation_error,
    format_validation_error,
)
from .reports import DryRunReport, ValidationReport
from .validation import validate_system_basic

__all__ = [
    "DryRunReport",
    "TranslatorProtocol",
    "ValidationReport",
    "create_empty_preview",
    "find_closest_match",
    "format_mapping_error",
    "format_translation_error",
    "format_validation_error",
    "validate_system_basic",
]
