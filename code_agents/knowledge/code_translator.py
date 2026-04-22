"""Code translation between programming languages using pattern-based transformations.

Produces reasonable scaffolding by applying regex-based transformations to source
code.  Uses ``code_agents.parsers`` for symbol extraction so that class/function
structure is preserved across languages.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.knowledge.code_translator")

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TranslationResult:
    """Result of translating a single source file."""
    source_path: str
    target_path: str
    source_lang: str
    target_lang: str
    code: str
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Language aliases & extension maps
# ---------------------------------------------------------------------------

LANG_ALIASES: dict[str, str] = {
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "rb": "ruby",
    "rs": "rust",
    "go": "go",
    "java": "java",
}

_LANG_TO_EXT: dict[str, str] = {
    "python": ".py",
    "javascript": ".js",
    "typescript": ".ts",
    "java": ".java",
    "go": ".go",
    "ruby": ".rb",
    "rust": ".rs",
}

_EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rb": "ruby",
    ".rs": "rust",
}

# ---------------------------------------------------------------------------
# Translator
# ---------------------------------------------------------------------------

class CodeTranslator:
    """Regex-based code translator.  Not AI-powered — produces scaffolding."""

    def __init__(self, cwd: str = ""):
        self.cwd = cwd or os.getcwd()

    # ---- public API -------------------------------------------------------

    def translate_file(self, source_path: str, target_lang: str) -> TranslationResult:
        """Translate *source_path* to *target_lang* and return a ``TranslationResult``."""
        target_lang = LANG_ALIASES.get(target_lang, target_lang).lower()
        abs_path = os.path.join(self.cwd, source_path) if not os.path.isabs(source_path) else source_path
        source_lang = self._detect_language(abs_path)

        if source_lang == "unknown":
            return TranslationResult(
                source_path=source_path,
                target_path=source_path,
                source_lang="unknown",
                target_lang=target_lang,
                code="",
                warnings=[f"Could not detect language for {source_path}"],
            )

        source_text = Path(abs_path).read_text(encoding="utf-8")

        # Parse symbols for structure-aware translation
        symbols = self._parse_symbols(abs_path, source_lang)

        pair_key = f"{source_lang}_to_{target_lang}"
        handler = getattr(self, f"_{pair_key}", None)

        warnings: list[str] = []
        if handler is None:
            warnings.append(
                f"No dedicated transformer for {source_lang} -> {target_lang}; "
                "returning generic comment scaffold."
            )
            code = self._generic_scaffold(source_text, source_lang, target_lang, symbols)
        else:
            code = handler(source_text, symbols)

        if source_lang == target_lang:
            warnings.append("Source and target languages are the same.")

        target_path = self._generate_target_path(source_path, target_lang)
        logger.info(
            "Translated %s (%s) -> %s (%s), %d warnings",
            source_path, source_lang, target_path, target_lang, len(warnings),
        )
        return TranslationResult(
            source_path=source_path,
            target_path=target_path,
            source_lang=source_lang,
            target_lang=target_lang,
            code=code,
            warnings=warnings,
        )

    # ---- language detection -----------------------------------------------

    def _detect_language(self, path: str) -> str:
        ext = Path(path).suffix.lower()
        return _EXT_TO_LANG.get(ext, "unknown")

    # ---- symbol extraction ------------------------------------------------

    def _parse_symbols(self, path: str, language: str):
        """Return parsed ``ModuleInfo`` from the parsers package."""
        try:
            from code_agents.parsers import parse_file
            return parse_file(path, language)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Symbol parsing failed for %s: %s", path, exc)
            return None

    # ---- target path generation -------------------------------------------

    def _generate_target_path(self, source_path: str, target_lang: str) -> str:
        ext = _LANG_TO_EXT.get(target_lang, ".txt")
        stem = Path(source_path).stem
        parent = str(Path(source_path).parent)
        return os.path.join(parent, f"{stem}{ext}")

    # ======================================================================
    # Python -> *
    # ======================================================================

    def _python_to_javascript(self, source: str, symbols) -> str:
        lines = source.splitlines()
        out: list[str] = []
        for line in lines:
            converted = self._py_line_to_js(line)
            out.append(converted)
        return "\n".join(out)

    def _python_to_java(self, source: str, symbols) -> str:
        lines = source.splitlines()
        out: list[str] = []
        class_name = "Translated"
        if symbols and symbols.symbols:
            for s in symbols.symbols:
                if s.kind == "class":
                    class_name = s.name
                    break

        out.append(f"public class {class_name} {{")
        out.append("")

        in_class = False
        indent_base = "    "

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                comment = stripped.lstrip("#").strip() if stripped.startswith("#") else ""
                if comment:
                    out.append(f"{indent_base}// {comment}")
                else:
                    out.append("")
                continue

            if stripped.startswith("import ") or stripped.startswith("from "):
                out.append(f"{indent_base}// {stripped}")
                continue

            if stripped.startswith("class "):
                in_class = True
                continue

            converted = self._py_line_to_java(stripped, indent_base)
            out.append(converted)

        out.append("}")
        return "\n".join(out)

    def _python_to_go(self, source: str, symbols) -> str:
        lines = source.splitlines()
        out: list[str] = ["package main", "", "import \"fmt\"", ""]

        # Collect class names -> struct
        class_names: list[str] = []
        if symbols and symbols.symbols:
            for s in symbols.symbols:
                if s.kind == "class":
                    class_names.append(s.name)

        for cls in class_names:
            out.append(f"type {cls} struct {{")
            out.append("}")
            out.append("")

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                comment = stripped.lstrip("#").strip() if stripped.startswith("#") else ""
                if comment:
                    out.append(f"// {comment}")
                else:
                    out.append("")
                continue

            if stripped.startswith("import ") or stripped.startswith("from "):
                continue

            if stripped.startswith("class "):
                continue

            if stripped.startswith("def "):
                func_line = self._py_def_to_go(stripped)
                out.append(func_line)
                continue

            converted = self._py_line_to_go(stripped)
            out.append(converted)

        return "\n".join(out)

    # ======================================================================
    # JavaScript -> *
    # ======================================================================

    def _javascript_to_python(self, source: str, symbols) -> str:
        lines = source.splitlines()
        out: list[str] = []
        for line in lines:
            converted = self._js_line_to_py(line)
            out.append(converted)
        return "\n".join(out)

    def _javascript_to_typescript(self, source: str, symbols) -> str:
        lines = source.splitlines()
        out: list[str] = []
        for line in lines:
            converted = self._js_line_to_ts(line)
            out.append(converted)
        return "\n".join(out)

    # ======================================================================
    # Line-level transformation helpers
    # ======================================================================

    # -- Python -> JavaScript helpers --

    def _py_line_to_js(self, line: str) -> str:
        indent = len(line) - len(line.lstrip())
        prefix = line[:indent]
        stripped = line.strip()

        if not stripped:
            return ""
        if stripped.startswith("#"):
            return f"{prefix}// {stripped.lstrip('#').strip()}"

        # def -> function
        m = re.match(r"def\s+(\w+)\s*\((.*?)\)\s*(?:->.*?)?:", stripped)
        if m:
            fname, params = m.group(1), m.group(2)
            params = self._strip_py_type_hints(params)
            params = params.replace("self, ", "").replace("self", "")
            return f"{prefix}function {fname}({params}) {{"

        # class
        m = re.match(r"class\s+(\w+)(?:\((.*?)\))?:", stripped)
        if m:
            cname = m.group(1)
            return f"{prefix}class {cname} {{"

        result = stripped
        # self. -> this.
        result = result.replace("self.", "this.")
        # print -> console.log
        result = re.sub(r"\bprint\s*\(", "console.log(", result)
        # None -> null
        result = re.sub(r"\bNone\b", "null", result)
        # True/False -> true/false
        result = re.sub(r"\bTrue\b", "true", result)
        result = re.sub(r"\bFalse\b", "false", result)
        # and/or/not
        result = re.sub(r"\band\b", "&&", result)
        result = re.sub(r"\bor\b", "||", result)
        result = re.sub(r"\bnot\b", "!", result)
        # elif -> else if
        result = re.sub(r"^elif\s+", "} else if (", result)
        # if ...: -> if (...) {
        m2 = re.match(r"^if\s+(.+):$", result)
        if m2:
            result = f"if ({m2.group(1)}) {{"
        # else: -> } else {
        if result.strip() == "else:":
            result = "} else {"
        # return
        result = result.rstrip(":")

        return f"{prefix}{result}"

    # -- Python -> Java helpers --

    def _py_line_to_java(self, stripped: str, indent: str) -> str:
        # def -> public method
        m = re.match(r"def\s+(\w+)\s*\((.*?)\)\s*(?:->\s*([\w\[\],\s]+))?:", stripped)
        if m:
            fname, params, ret = m.group(1), m.group(2), m.group(3)
            params = params.replace("self, ", "").replace("self", "")
            params = self._py_params_to_java(params)
            ret_type = self._py_type_to_java(ret) if ret else "void"
            if fname == "__init__":
                return f"{indent}public {ret_type} {fname}({params}) {{"
            return f"{indent}public {ret_type} {fname}({params}) {{"

        result = stripped
        result = result.replace("self.", "this.")
        result = re.sub(r"\bprint\s*\(", "System.out.println(", result)
        result = re.sub(r"\bNone\b", "null", result)
        result = re.sub(r"\bTrue\b", "true", result)
        result = re.sub(r"\bFalse\b", "false", result)
        result = re.sub(r"\band\b", "&&", result)
        result = re.sub(r"\bor\b", "||", result)
        result = result.rstrip(":")
        if not result.endswith("{") and not result.endswith("}"):
            result = result + ";"
        return f"{indent}{result}"

    # -- Python -> Go helpers --

    def _py_def_to_go(self, stripped: str) -> str:
        m = re.match(r"def\s+(\w+)\s*\((.*?)\)\s*(?:->\s*([\w\[\],\s]+))?:", stripped)
        if not m:
            return f"// {stripped}"
        fname, params, ret = m.group(1), m.group(2), m.group(3)
        params = params.replace("self, ", "").replace("self", "")
        go_params = self._py_params_to_go(params)
        ret_type = self._py_type_to_go(ret) if ret else ""
        ret_str = f" {ret_type}" if ret_type else ""
        # Capitalize first letter for exported Go funcs
        go_name = fname[0].upper() + fname[1:] if fname and fname[0].islower() else fname
        return f"func {go_name}({go_params}){ret_str} {{"

    def _py_line_to_go(self, stripped: str) -> str:
        result = stripped
        result = result.replace("self.", "")
        result = re.sub(r"\bprint\s*\(", "fmt.Println(", result)
        result = re.sub(r"\bNone\b", "nil", result)
        result = re.sub(r"\bTrue\b", "true", result)
        result = re.sub(r"\bFalse\b", "false", result)
        result = re.sub(r"\band\b", "&&", result)
        result = re.sub(r"\bor\b", "||", result)
        result = result.rstrip(":")
        return f"\t{result}"

    # -- JavaScript -> Python helpers --

    def _js_line_to_py(self, line: str) -> str:
        indent = len(line) - len(line.lstrip())
        prefix = line[:indent]
        stripped = line.strip()

        if not stripped:
            return ""
        if stripped.startswith("//"):
            return f"{prefix}# {stripped.lstrip('/').strip()}"
        if stripped.startswith("/*") or stripped.startswith("*"):
            return f"{prefix}# {stripped.lstrip('/*').rstrip('*/').strip()}"

        # function -> def
        m = re.match(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\((.*?)\)\s*\{?", stripped)
        if m:
            fname, params = m.group(1), m.group(2)
            params = self._strip_ts_types(params)
            return f"{prefix}def {fname}({params}):"

        # const/let/var
        m = re.match(r"(?:const|let|var)\s+(\w+)\s*=\s*(.+?);\s*$", stripped)
        if m:
            val = m.group(2)
            val = re.sub(r"\bnull\b", "None", val)
            val = re.sub(r"\bundefined\b", "None", val)
            val = re.sub(r"\btrue\b", "True", val)
            val = re.sub(r"\bfalse\b", "False", val)
            return f"{prefix}{m.group(1)} = {val}"

        # arrow function
        m = re.match(r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\((.*?)\)\s*=>\s*\{?", stripped)
        if m:
            fname, params = m.group(1), m.group(2)
            params = self._strip_ts_types(params)
            return f"{prefix}def {fname}({params}):"

        result = stripped
        # this. -> self.
        result = result.replace("this.", "self.")
        # console.log -> print
        result = re.sub(r"console\.log\s*\(", "print(", result)
        # null -> None
        result = re.sub(r"\bnull\b", "None", result)
        result = re.sub(r"\bundefined\b", "None", result)
        # true/false
        result = re.sub(r"\btrue\b", "True", result)
        result = re.sub(r"\bfalse\b", "False", result)
        # && / ||
        result = re.sub(r"&&", "and", result)
        result = re.sub(r"\|\|", "or", result)
        # remove trailing semicolons and braces
        result = result.rstrip(";").rstrip("{").rstrip("}").rstrip()

        return f"{prefix}{result}"

    # -- JavaScript -> TypeScript helpers --

    def _js_line_to_ts(self, line: str) -> str:
        """Add basic type annotations to JS code to make it TS."""
        stripped = line.strip()

        # function params: add ': any' to untyped params
        m = re.match(r"((?:export\s+)?(?:async\s+)?function\s+\w+\s*)\((.*?)\)(.*)", stripped)
        if m:
            prefix_fn, params, rest = m.group(1), m.group(2), m.group(3)
            typed_params = self._add_any_types(params)
            # Add return type
            if ": " not in rest.split("{")[0] if "{" in rest else rest:
                rest = rest.replace("{", ": any {", 1) if "{" in rest else rest + ": any"
            indent = len(line) - len(line.lstrip())
            return f"{line[:indent]}{prefix_fn}({typed_params}){rest}"

        # const x = ... -> const x: any = ...
        m = re.match(r"((?:const|let|var)\s+\w+)\s*(=\s*.+)", stripped)
        if m and ": " not in m.group(1):
            indent = len(line) - len(line.lstrip())
            return f"{line[:indent]}{m.group(1)}: any {m.group(2)}"

        return line

    # ======================================================================
    # Generic scaffold (unsupported pairs)
    # ======================================================================

    def _generic_scaffold(self, source: str, src_lang: str, tgt_lang: str, symbols) -> str:
        """Generate a commented scaffold for unsupported language pairs."""
        comment_prefix = "//" if tgt_lang in ("javascript", "typescript", "java", "go", "rust") else "#"
        lines = [
            f"{comment_prefix} Translated from {src_lang} to {tgt_lang} (scaffold)",
            f"{comment_prefix} Manual review required — not all patterns translated.",
            "",
        ]

        if symbols and symbols.symbols:
            lines.append(f"{comment_prefix} Symbols from source:")
            for s in symbols.symbols:
                lines.append(f"{comment_prefix}   {s.kind}: {s.name}")
            lines.append("")

        for src_line in source.splitlines():
            lines.append(f"{comment_prefix} {src_line}" if src_line.strip() else "")

        return "\n".join(lines)

    # ======================================================================
    # Utility helpers
    # ======================================================================

    def _strip_py_type_hints(self, params: str) -> str:
        """Remove Python type hints from parameter string."""
        parts = [p.strip() for p in params.split(",") if p.strip()]
        cleaned = []
        for p in parts:
            name = p.split(":")[0].strip()
            if "=" in p:
                default = p.split("=", 1)[1].strip()
                name = p.split(":")[0].strip().split("=")[0].strip()
                cleaned.append(f"{name}={default}")
            else:
                cleaned.append(name)
        return ", ".join(cleaned)

    def _py_params_to_java(self, params: str) -> str:
        """Convert Python params to Java-style typed params."""
        if not params.strip():
            return ""
        parts = [p.strip() for p in params.split(",") if p.strip()]
        java_parts = []
        for p in parts:
            if ":" in p:
                name, typ = p.split(":", 1)
                java_type = self._py_type_to_java(typ.strip())
                java_parts.append(f"{java_type} {name.strip()}")
            else:
                name = p.split("=")[0].strip()
                java_parts.append(f"Object {name}")
        return ", ".join(java_parts)

    def _py_type_to_java(self, py_type: str) -> str:
        """Map a Python type hint to a Java type."""
        if not py_type:
            return "Object"
        py_type = py_type.strip()
        mapping = {
            "str": "String",
            "int": "int",
            "float": "double",
            "bool": "boolean",
            "list": "List<Object>",
            "dict": "Map<String, Object>",
            "None": "void",
            "Optional": "Object",
            "Any": "Object",
        }
        return mapping.get(py_type, "Object")

    def _py_params_to_go(self, params: str) -> str:
        """Convert Python params to Go-style typed params."""
        if not params.strip():
            return ""
        parts = [p.strip() for p in params.split(",") if p.strip()]
        go_parts = []
        for p in parts:
            if ":" in p:
                name, typ = p.split(":", 1)
                go_type = self._py_type_to_go(typ.strip())
                go_parts.append(f"{name.strip()} {go_type}")
            else:
                name = p.split("=")[0].strip()
                go_parts.append(f"{name} interface{{}}")
        return ", ".join(go_parts)

    def _py_type_to_go(self, py_type: str) -> str:
        """Map a Python type hint to a Go type."""
        if not py_type:
            return "interface{}"
        py_type = py_type.strip()
        mapping = {
            "str": "string",
            "int": "int",
            "float": "float64",
            "bool": "bool",
            "list": "[]interface{}",
            "dict": "map[string]interface{}",
            "None": "",
            "Optional": "interface{}",
            "Any": "interface{}",
        }
        return mapping.get(py_type, "interface{}")

    def _strip_ts_types(self, params: str) -> str:
        """Strip TypeScript type annotations from params."""
        parts = [p.strip() for p in params.split(",") if p.strip()]
        cleaned = []
        for p in parts:
            name = p.split(":")[0].strip()
            if "=" in name:
                name = name.split("=")[0].strip()
            cleaned.append(name)
        return ", ".join(cleaned)

    def _add_any_types(self, params: str) -> str:
        """Add ': any' to untyped JS function params for TS conversion."""
        if not params.strip():
            return ""
        parts = [p.strip() for p in params.split(",") if p.strip()]
        typed = []
        for p in parts:
            if ":" not in p:
                name = p.split("=")[0].strip()
                default = ""
                if "=" in p:
                    default = " = " + p.split("=", 1)[1].strip()
                typed.append(f"{name}: any{default}")
            else:
                typed.append(p)
        return ", ".join(typed)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_translation(result: TranslationResult) -> str:
    """Format a translation result as a side-by-side summary."""
    lines: list[str] = []
    lines.append(f"  Translation: {result.source_lang} -> {result.target_lang}")
    lines.append(f"  Source: {result.source_path}")
    lines.append(f"  Target: {result.target_path}")
    lines.append(f"  Lines:  {len(result.code.splitlines())}")
    if result.warnings:
        lines.append(f"  Warnings ({len(result.warnings)}):")
        for w in result.warnings:
            lines.append(f"    - {w}")
    lines.append("")
    lines.append("  --- translated code ---")
    for i, code_line in enumerate(result.code.splitlines(), 1):
        lines.append(f"  {i:4d} | {code_line}")
    lines.append("  --- end ---")
    return "\n".join(lines)
