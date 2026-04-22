"""Multi-language migration — translate entire modules between programming languages.

Scans a source directory, translates each file using :mod:`code_agents.code_translator`,
generates equivalent test stubs, and scaffolds the target project structure
(``go.mod``, ``package.json``, ``pom.xml``, etc.).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.knowledge.lang_migration")

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class MigrationResult:
    """Outcome of a full module migration."""

    source_dir: str
    target_dir: str
    target_lang: str
    translated_files: list[str] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    scaffold_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def total_files(self) -> int:
        return len(self.translated_files) + len(self.test_files) + len(self.scaffold_files)


# ---------------------------------------------------------------------------
# Language → extension / source detection
# ---------------------------------------------------------------------------

_SOURCE_EXTS: dict[str, list[str]] = {
    "python": [".py"],
    "javascript": [".js", ".jsx"],
    "typescript": [".ts", ".tsx"],
    "java": [".java"],
    "go": [".go"],
    "ruby": [".rb"],
    "rust": [".rs"],
}

_LANG_ALIASES: dict[str, str] = {
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "rb": "ruby",
    "rs": "rust",
    "go": "go",
    "java": "java",
}

_TARGET_EXT: dict[str, str] = {
    "python": ".py",
    "javascript": ".js",
    "typescript": ".ts",
    "java": ".java",
    "go": ".go",
    "ruby": ".rb",
    "rust": ".rs",
}

# Scaffold templates per language
_SCAFFOLD_TEMPLATES: dict[str, dict[str, str]] = {
    "go": {
        "go.mod": "module {module_name}\n\ngo 1.21\n",
    },
    "javascript": {
        "package.json": (
            '{{\n  "name": "{module_name}",\n  "version": "1.0.0",\n'
            '  "description": "Migrated from {source_lang}",\n'
            '  "main": "index.js",\n  "scripts": {{\n'
            '    "test": "jest"\n  }},\n'
            '  "devDependencies": {{\n    "jest": "^29.0.0"\n  }}\n}}\n'
        ),
    },
    "typescript": {
        "package.json": (
            '{{\n  "name": "{module_name}",\n  "version": "1.0.0",\n'
            '  "description": "Migrated from {source_lang}",\n'
            '  "main": "index.ts",\n  "scripts": {{\n'
            '    "build": "tsc",\n    "test": "jest"\n  }},\n'
            '  "devDependencies": {{\n'
            '    "typescript": "^5.0.0",\n    "jest": "^29.0.0",\n'
            '    "ts-jest": "^29.0.0",\n    "@types/jest": "^29.0.0"\n'
            "  }}\n}}\n"
        ),
        "tsconfig.json": (
            '{{\n  "compilerOptions": {{\n    "target": "es2020",\n'
            '    "module": "commonjs",\n    "strict": true,\n'
            '    "outDir": "./dist"\n  }},\n  "include": ["*.ts"]\n}}\n'
        ),
    },
    "java": {
        "pom.xml": (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<project xmlns="http://maven.apache.org/POM/4.0.0"\n'
            '         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n'
            '         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 '
            'http://maven.apache.org/xsd/maven-4.0.0.xsd">\n'
            "  <modelVersion>4.0.0</modelVersion>\n"
            "  <groupId>com.migrated</groupId>\n"
            "  <artifactId>{module_name}</artifactId>\n"
            "  <version>1.0.0</version>\n"
            "  <properties>\n"
            "    <maven.compiler.source>17</maven.compiler.source>\n"
            "    <maven.compiler.target>17</maven.compiler.target>\n"
            "  </properties>\n"
            "  <dependencies>\n"
            "    <dependency>\n"
            "      <groupId>junit</groupId>\n"
            "      <artifactId>junit</artifactId>\n"
            "      <version>4.13.2</version>\n"
            "      <scope>test</scope>\n"
            "    </dependency>\n"
            "  </dependencies>\n"
            "</project>\n"
        ),
    },
    "python": {
        "pyproject.toml": (
            "[tool.poetry]\n"
            'name = "{module_name}"\n'
            'version = "1.0.0"\n'
            'description = "Migrated from {source_lang}"\n\n'
            "[tool.poetry.dependencies]\n"
            'python = "^3.10"\n\n'
            "[tool.pytest.ini_options]\n"
            'testpaths = ["tests"]\n'
        ),
    },
}

# Test template per language
_TEST_TEMPLATES: dict[str, str] = {
    "python": (
        '"""Auto-generated test stub for {module_name}."""\n\n'
        "import pytest\n\n\n"
        "class Test{class_name}:\n"
        '    """Tests for {module_name}."""\n\n'
        "    def test_placeholder(self):\n"
        "        # TODO: implement real tests\n"
        "        assert True\n"
    ),
    "javascript": (
        "// Auto-generated test stub for {module_name}\n\n"
        "describe('{module_name}', () => {{\n"
        "  test('placeholder', () => {{\n"
        "    // TODO: implement real tests\n"
        "    expect(true).toBe(true);\n"
        "  }});\n"
        "}});\n"
    ),
    "typescript": (
        "// Auto-generated test stub for {module_name}\n\n"
        "describe('{module_name}', () => {{\n"
        "  test('placeholder', () => {{\n"
        "    // TODO: implement real tests\n"
        "    expect(true).toBe(true);\n"
        "  }});\n"
        "}});\n"
    ),
    "go": (
        "package {package_name}\n\n"
        'import "testing"\n\n'
        "func TestPlaceholder(t *testing.T) {{\n"
        "\t// TODO: implement real tests\n"
        "\tt.Log(\"{module_name} tests\")\n"
        "}}\n"
    ),
    "java": (
        "import org.junit.Test;\n"
        "import static org.junit.Assert.*;\n\n"
        "public class {class_name}Test {{\n"
        "    @Test\n"
        "    public void testPlaceholder() {{\n"
        "        // TODO: implement real tests\n"
        "        assertTrue(true);\n"
        "    }}\n"
        "}}\n"
    ),
}


# ---------------------------------------------------------------------------
# Migrator
# ---------------------------------------------------------------------------


class LanguageMigrator:
    """Migrate an entire module directory to a target language."""

    def __init__(self, cwd: str):
        self.cwd = cwd or os.getcwd()

    # ---- public API -------------------------------------------------------

    def migrate_module(
        self,
        source_dir: str,
        target_lang: str,
        output_dir: Optional[str] = None,
    ) -> MigrationResult:
        """Migrate all source files in *source_dir* to *target_lang*.

        1. Scan all source files in directory
        2. Translate each file (reuse code_translator.py)
        3. Generate equivalent test files
        4. Create project structure (go.mod/package.json/pom.xml)
        """
        target_lang = _LANG_ALIASES.get(target_lang.lower(), target_lang.lower())

        src = Path(self.cwd, source_dir).resolve()
        out = Path(output_dir).resolve() if output_dir else src.parent / f"{src.name}_{target_lang}"

        result = MigrationResult(
            source_dir=str(src),
            target_dir=str(out),
            target_lang=target_lang,
        )

        if not src.is_dir():
            result.errors.append(f"Source directory not found: {src}")
            logger.error("Source directory not found: %s", src)
            return result

        if target_lang not in _TARGET_EXT:
            result.errors.append(f"Unsupported target language: {target_lang}")
            logger.error("Unsupported target language: %s", target_lang)
            return result

        # Collect source files
        source_files = self._scan_source_files(src)
        if not source_files:
            result.warnings.append("No source files found in directory")
            logger.warning("No source files found in %s", src)
            return result

        logger.info(
            "Migrating %d files from %s to %s", len(source_files), src, target_lang
        )

        # Create output directory
        out.mkdir(parents=True, exist_ok=True)

        # Translate each file
        from code_agents.knowledge.code_translator import CodeTranslator

        translator = CodeTranslator(cwd=self.cwd)

        for src_file in source_files:
            rel = src_file.relative_to(src)
            stem = rel.stem
            target_ext = _TARGET_EXT[target_lang]
            target_path = out / rel.with_suffix(target_ext)

            try:
                tr_result = translator.translate_file(str(src_file), target_lang)
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(tr_result.code, encoding="utf-8")
                result.translated_files.append(str(target_path))
                result.warnings.extend(tr_result.warnings)
                logger.debug("Translated %s -> %s", src_file, target_path)
            except Exception as exc:
                msg = f"Failed to translate {src_file}: {exc}"
                result.errors.append(msg)
                logger.error(msg)

        # Generate test stubs
        test_files = self._migrate_tests(source_files, target_lang, out)
        result.test_files = test_files

        # Create project scaffold
        scaffold = self._create_project_scaffold(target_lang, out, src.name)
        result.scaffold_files = scaffold

        logger.info(
            "Migration complete: %d translated, %d tests, %d scaffold files",
            len(result.translated_files),
            len(result.test_files),
            len(result.scaffold_files),
        )

        return result

    # ---- internals --------------------------------------------------------

    def _scan_source_files(self, directory: Path) -> list[Path]:
        """Scan directory for source files of any recognized language."""
        all_exts = set()
        for exts in _SOURCE_EXTS.values():
            all_exts.update(exts)

        files: list[Path] = []
        for f in sorted(directory.rglob("*")):
            if f.is_file() and f.suffix in all_exts:
                # Skip test files, __pycache__, node_modules, etc.
                parts = f.parts
                skip = any(
                    p in ("__pycache__", "node_modules", ".git", "venv", ".venv")
                    for p in parts
                )
                if not skip:
                    files.append(f)
        return files

    def _create_project_scaffold(
        self, target_lang: str, out_dir: Path, module_name: str
    ) -> list[str]:
        """Create project structure files for the target language."""
        templates = _SCAFFOLD_TEMPLATES.get(target_lang, {})
        created: list[str] = []

        for filename, template in templates.items():
            target = out_dir / filename
            if not target.exists():
                content = template.format(
                    module_name=module_name,
                    source_lang="source",
                )
                target.write_text(content, encoding="utf-8")
                created.append(str(target))
                logger.debug("Created scaffold: %s", target)

        return created

    def _migrate_tests(
        self, source_files: list[Path], target_lang: str, out_dir: Path
    ) -> list[str]:
        """Generate test stub files for each source file."""
        template = _TEST_TEMPLATES.get(target_lang)
        if not template:
            return []

        test_dir = out_dir / ("tests" if target_lang != "go" else "")
        if target_lang != "go":
            test_dir.mkdir(parents=True, exist_ok=True)

        created: list[str] = []
        target_ext = _TARGET_EXT[target_lang]

        for src_file in source_files:
            stem = src_file.stem
            # Skip files that are already tests
            if stem.startswith("test_") or stem.endswith("_test"):
                continue

            class_name = _to_class_name(stem)
            package_name = stem.replace("-", "_").replace(" ", "_").lower()

            if target_lang == "go":
                test_filename = f"{stem}_test{target_ext}"
                test_path = out_dir / test_filename
            elif target_lang == "java":
                test_filename = f"{class_name}Test{target_ext}"
                test_path = test_dir / test_filename
            elif target_lang in ("javascript", "typescript"):
                test_filename = f"{stem}.test{target_ext}"
                test_path = test_dir / test_filename
            else:
                test_filename = f"test_{stem}{target_ext}"
                test_path = test_dir / test_filename

            content = template.format(
                module_name=stem,
                class_name=class_name,
                package_name=package_name,
            )
            test_path.parent.mkdir(parents=True, exist_ok=True)
            test_path.write_text(content, encoding="utf-8")
            created.append(str(test_path))
            logger.debug("Created test: %s", test_path)

        return created


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _to_class_name(stem: str) -> str:
    """Convert file stem to PascalCase class name."""
    parts = stem.replace("-", "_").split("_")
    return "".join(p.capitalize() for p in parts if p)


def format_migration_result(result: MigrationResult) -> str:
    """Format migration result for terminal display."""
    lines: list[str] = []
    lines.append(f"  Migration: {result.source_dir} -> {result.target_dir}")
    lines.append(f"  Target language: {result.target_lang}")
    lines.append("")

    if result.translated_files:
        lines.append(f"  Translated files ({len(result.translated_files)}):")
        for f in result.translated_files:
            lines.append(f"    {f}")
        lines.append("")

    if result.test_files:
        lines.append(f"  Test stubs ({len(result.test_files)}):")
        for f in result.test_files:
            lines.append(f"    {f}")
        lines.append("")

    if result.scaffold_files:
        lines.append(f"  Scaffold files ({len(result.scaffold_files)}):")
        for f in result.scaffold_files:
            lines.append(f"    {f}")
        lines.append("")

    if result.warnings:
        lines.append(f"  Warnings ({len(result.warnings)}):")
        for w in result.warnings:
            lines.append(f"    ! {w}")
        lines.append("")

    if result.errors:
        lines.append(f"  Errors ({len(result.errors)}):")
        for e in result.errors:
            lines.append(f"    X {e}")
        lines.append("")

    lines.append(f"  Total: {result.total_files} files generated")
    return "\n".join(lines)
