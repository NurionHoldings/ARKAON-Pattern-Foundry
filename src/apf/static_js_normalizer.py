"""Parser-only minified JS normalization and structural de-obfuscation without execution."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256

_DYNAMIC_EXEC = re.compile(
    r"(?i)\b(eval|Function|setTimeout|setInterval)\s*\(|new\s+Function\b|document\.write\s*\("
)
_IMPORT = re.compile(r"""^\s*import\s.+['"]([^'"]+)['"]""")
_EXPORT = re.compile(r"""^\s*export\s+(?:default\s+)?(?:function|class|const|let|var)?\s*(\w*)""")
_ROUTE = re.compile(r"""['"](/(?:[A-Za-z0-9_\-/{:.}]+))['"]""")
_FETCH = re.compile(r"""(?i)\b(fetch|axios\.(?:get|post|put|delete))\s*\(""")
_UNICODE = re.compile(r"\\u([0-9a-fA-F]{4})")
_HEX = re.compile(r"\\x([0-9a-fA-F]{2})")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"//[^\n]*")
_STRING_LITERAL = re.compile(r"""('(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*")""")


class StaticJsRejected(ValueError):
    pass


@dataclass(frozen=True)
class NormalizedJsStructure:
    source_path: str
    original_bytes: int
    normalized_bytes: int
    import_targets: tuple[str, ...]
    export_symbols: tuple[str, ...]
    route_refs: tuple[str, ...]
    fetch_patterns: tuple[str, ...]
    identifier_shape_digest: str
    structure_digest: str
    deobfuscated_preview_lines: tuple[str, ...]
    dynamic_execution_detected: bool = False

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.static-js-structure/v1",
            "source_path": self.source_path,
            "original_bytes": self.original_bytes,
            "normalized_bytes": self.normalized_bytes,
            "import_targets": list(self.import_targets),
            "export_symbols": list(self.export_symbols),
            "route_refs": list(self.route_refs),
            "fetch_patterns": list(self.fetch_patterns),
            "identifier_shape_digest": self.identifier_shape_digest,
            "structure_digest": self.structure_digest,
            "deobfuscated_preview_lines": list(self.deobfuscated_preview_lines),
            "dynamic_execution_detected": self.dynamic_execution_detected,
            "verbatim_storage": False,
        }


def decode_obfuscated_escapes(text: str) -> str:
    """Decode unicode and hex escapes for structural reading only."""

    def replace_unicode(match: re.Match[str]) -> str:
        return chr(int(match.group(1), 16))

    def replace_hex(match: re.Match[str]) -> str:
        return chr(int(match.group(1), 16))

    decoded = _UNICODE.sub(replace_unicode, text)
    return _HEX.sub(replace_hex, decoded)


def strip_comments(source: str) -> str:
    without_block = _BLOCK_COMMENT.sub("", source)
    return _LINE_COMMENT.sub("", without_block)


def collapse_whitespace(source: str) -> str:
    return re.sub(r"\s+", " ", source.strip())


def abstract_identifiers(source: str) -> str:
    """Replace identifiers with shape tokens; string literals become [STR]."""

    def replace_string(match: re.Match[str]) -> str:
        return "[STR]"

    without_strings = _STRING_LITERAL.sub(replace_string, source)
    return re.sub(r"\b[A-Za-z_$][\w$]*\b", lambda match: _shape_token(match.group(0)), without_strings)


def _shape_token(identifier: str) -> str:
    if identifier in {"if", "else", "for", "while", "return", "const", "let", "var", "function", "class"}:
        return identifier
    length = len(identifier)
    if length <= 2:
        return "idS"
    if length <= 6:
        return "idM"
    return "idL"


def normalize_minified_js(*, source_path: str, content: str, max_bytes: int = 524_288) -> NormalizedJsStructure:
    encoded = content.encode("utf-8", errors="ignore")
    if len(encoded) > max_bytes:
        raise StaticJsRejected("js file exceeds observation size limit")
    if not content.strip():
        raise StaticJsRejected("empty js source")
    dynamic = bool(_DYNAMIC_EXEC.search(content))
    decoded = decode_obfuscated_escapes(strip_comments(content))
    normalized = collapse_whitespace(decoded)
    imports: list[str] = []
    exports: list[str] = []
    routes: set[str] = set()
    fetches: set[str] = set()
    for line in normalized.split(";"):
        stripped = line.strip()
        if match := _IMPORT.match(stripped):
            imports.append(match.group(1))
        if match := _EXPORT.match(stripped):
            symbol = match.group(1) or "default"
            exports.append(symbol)
        for route in _ROUTE.findall(stripped):
            routes.add(route.split("{", 1)[0].rstrip("/") or "/")
        for fetch in _FETCH.findall(stripped):
            fetches.add(fetch.lower())
    identifier_digest = sha256(abstract_identifiers(normalized).encode()).hexdigest()
    structure = {
        "imports": sorted(set(imports)),
        "exports": sorted(set(exports)),
        "routes": sorted(routes),
        "fetch_patterns": sorted(fetches),
        "dynamic_execution_detected": dynamic,
    }
    structure_digest = sha256(json.dumps(structure, sort_keys=True).encode()).hexdigest()
    preview = tuple(
        item
        for item in (
            f"imports={len(set(imports))}",
            f"exports={len(set(exports))}",
            f"routes={','.join(sorted(routes)[:5]) or '/'}",
            f"fetch={','.join(sorted(fetches)[:3]) or 'none'}",
            "dynamic_execution=detected" if dynamic else "dynamic_execution=none",
        )
    )
    return NormalizedJsStructure(
        source_path=source_path,
        original_bytes=len(encoded),
        normalized_bytes=len(normalized.encode()),
        import_targets=tuple(sorted(set(imports))),
        export_symbols=tuple(sorted(set(exports))),
        route_refs=tuple(sorted(routes)),
        fetch_patterns=tuple(sorted(fetches)),
        identifier_shape_digest=identifier_digest,
        structure_digest=structure_digest,
        deobfuscated_preview_lines=preview,
        dynamic_execution_detected=dynamic,
    )


def verify_no_verbatim_copy(*, original: str, abstract: str, min_similarity_ratio: float = 0.85) -> None:
    """Reject when abstract output still carries too much verbatim competitor source."""
    if not original or not abstract:
        raise StaticJsRejected("verbatim copy verification requires content")
    original_norm = collapse_whitespace(strip_comments(original)).casefold()
    abstract_norm = abstract.casefold()
    if original_norm and original_norm in abstract_norm:
        raise StaticJsRejected("verbatim source must not be stored in observation output")
    original_tokens = set(original_norm.split())
    abstract_tokens = set(abstract_norm.split())
    if not original_tokens:
        return
    overlap = len(original_tokens & abstract_tokens) / len(original_tokens)
    if overlap >= min_similarity_ratio:
        raise StaticJsRejected("observation output is too similar to verbatim source")
