"""Tests for screenshot_to_code module."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.ui.screenshot_to_code import (
    GeneratedUI,
    ScreenshotToCode,
    UIComponent,
    TEMPLATES,
    _match_template,
    format_generated_ui,
)


@pytest.fixture
def tmp_cwd(tmp_path):
    """Provide a temporary working directory."""
    return str(tmp_path)


@pytest.fixture
def generator(tmp_cwd):
    return ScreenshotToCode(cwd=tmp_cwd)


# ---------------------------------------------------------------------------
# TestDetectFramework
# ---------------------------------------------------------------------------

class TestDetectFramework:
    """Test framework auto-detection from project files."""

    def test_detect_react_from_package_json(self, tmp_cwd):
        pkg = Path(tmp_cwd) / "package.json"
        pkg.write_text(json.dumps({"dependencies": {"react": "^18.0.0", "react-dom": "^18.0.0"}}))
        gen = ScreenshotToCode(cwd=tmp_cwd)
        assert gen._detect_framework() == "react"

    def test_detect_vue_from_package_json(self, tmp_cwd):
        pkg = Path(tmp_cwd) / "package.json"
        pkg.write_text(json.dumps({"dependencies": {"vue": "^3.0.0"}}))
        gen = ScreenshotToCode(cwd=tmp_cwd)
        assert gen._detect_framework() == "vue"

    def test_detect_next_as_react(self, tmp_cwd):
        pkg = Path(tmp_cwd) / "package.json"
        pkg.write_text(json.dumps({"dependencies": {"next": "^13.0.0"}}))
        gen = ScreenshotToCode(cwd=tmp_cwd)
        assert gen._detect_framework() == "react"

    def test_detect_nuxt_as_vue(self, tmp_cwd):
        pkg = Path(tmp_cwd) / "package.json"
        pkg.write_text(json.dumps({"dependencies": {"nuxt": "^3.0.0"}}))
        gen = ScreenshotToCode(cwd=tmp_cwd)
        assert gen._detect_framework() == "vue"

    def test_detect_react_from_jsx_files(self, tmp_cwd):
        (Path(tmp_cwd) / "App.jsx").write_text("export default function App() {}")
        gen = ScreenshotToCode(cwd=tmp_cwd)
        assert gen._detect_framework() == "react"

    def test_detect_vue_from_vue_files(self, tmp_cwd):
        (Path(tmp_cwd) / "App.vue").write_text("<template></template>")
        gen = ScreenshotToCode(cwd=tmp_cwd)
        assert gen._detect_framework() == "vue"

    def test_default_to_html(self, tmp_cwd):
        gen = ScreenshotToCode(cwd=tmp_cwd)
        assert gen._detect_framework() == "html"

    def test_invalid_package_json(self, tmp_cwd):
        pkg = Path(tmp_cwd) / "package.json"
        pkg.write_text("not-valid-json")
        gen = ScreenshotToCode(cwd=tmp_cwd)
        assert gen._detect_framework() == "html"

    def test_angular_falls_back_to_html(self, tmp_cwd):
        pkg = Path(tmp_cwd) / "package.json"
        pkg.write_text(json.dumps({"dependencies": {"@angular/core": "^16.0.0"}}))
        gen = ScreenshotToCode(cwd=tmp_cwd)
        assert gen._detect_framework() == "html"


# ---------------------------------------------------------------------------
# TestGenerateHTML
# ---------------------------------------------------------------------------

class TestGenerateHTML:
    """Test HTML code generation."""

    def test_generates_valid_html(self, generator):
        result = generator.generate(description="login form", framework="html")
        assert result.framework == "html"
        assert "<!DOCTYPE html>" in result.code
        assert "</html>" in result.code

    def test_login_form_has_inputs(self, generator):
        result = generator.generate(description="login form", framework="html")
        assert "<input" in result.code
        assert 'type="email"' in result.code
        assert 'type="password"' in result.code

    def test_dashboard_has_stats(self, generator):
        result = generator.generate(description="dashboard overview", framework="html")
        assert "stat-card" in result.code

    def test_data_table_has_table(self, generator):
        result = generator.generate(description="data table with rows", framework="html")
        assert "<table" in result.code
        assert "<th" in result.code

    def test_card_grid_has_cards(self, generator):
        result = generator.generate(description="card grid", framework="html")
        assert "card" in result.code.lower()

    def test_sidebar_has_nav(self, generator):
        result = generator.generate(description="sidebar navigation", framework="html")
        assert "nav-item" in result.code

    def test_modal_dialog(self, generator):
        result = generator.generate(description="modal dialog confirm", framework="html")
        assert "modal" in result.code.lower()

    def test_default_template_on_unknown(self, generator):
        result = generator.generate(description="something totally random xyz", framework="html")
        assert result.code  # Should still produce code (fallback to dashboard)
        assert len(result.warnings) > 0


# ---------------------------------------------------------------------------
# TestGenerateReact
# ---------------------------------------------------------------------------

class TestGenerateReact:
    """Test React JSX generation."""

    def test_generates_react_component(self, generator):
        result = generator.generate(description="login form", framework="react")
        assert result.framework == "react"
        assert "import React" in result.code
        assert "export default" in result.code

    def test_react_login_has_state(self, generator):
        result = generator.generate(description="login form", framework="react")
        assert "useState" in result.code

    def test_react_dashboard(self, generator):
        result = generator.generate(description="dashboard analytics", framework="react")
        assert "export default" in result.code

    def test_react_data_table(self, generator):
        result = generator.generate(description="data table", framework="react")
        assert "export default" in result.code

    def test_react_fallback_for_unknown_template(self, generator):
        result = generator.generate(description="sidebar nav", framework="react")
        # Should still produce a React component even if template not available
        assert "export default" in result.code or "import React" in result.code


# ---------------------------------------------------------------------------
# TestGenerateVue
# ---------------------------------------------------------------------------

class TestGenerateVue:
    """Test Vue SFC generation."""

    def test_generates_vue_sfc(self, generator):
        result = generator.generate(description="login form", framework="vue")
        assert result.framework == "vue"
        assert "<template>" in result.code
        assert "<script" in result.code

    def test_vue_fallback(self, generator):
        result = generator.generate(description="unknown pattern", framework="vue")
        assert result.code  # Should still produce code


# ---------------------------------------------------------------------------
# TestTemplates
# ---------------------------------------------------------------------------

class TestTemplates:
    """Test that each template renders valid output."""

    @pytest.mark.parametrize("template_name", list(TEMPLATES.keys()))
    def test_html_template_renders(self, generator, template_name):
        code = generator._generate_html(template_name)
        assert "<!DOCTYPE html>" in code
        assert "</html>" in code

    def test_all_templates_have_keywords(self):
        for name, info in TEMPLATES.items():
            assert "keywords" in info, f"Template {name} missing keywords"
            assert len(info["keywords"]) > 0, f"Template {name} has no keywords"

    def test_match_template_login(self):
        assert _match_template("login page with sign in") == "login_form"

    def test_match_template_dashboard(self):
        assert _match_template("dashboard with metrics") == "dashboard"

    def test_match_template_table(self):
        assert _match_template("data table with pagination") == "data_table"

    def test_match_template_cards(self):
        assert _match_template("card grid layout") == "card_grid"

    def test_match_template_sidebar(self):
        assert _match_template("sidebar navigation menu") == "nav_sidebar"

    def test_match_template_modal(self):
        assert _match_template("modal dialog popup") == "modal_dialog"

    def test_match_template_none(self):
        assert _match_template("") is None

    def test_match_template_no_match(self):
        assert _match_template("xyzzy foobar") is None


# ---------------------------------------------------------------------------
# TestExtractComponents
# ---------------------------------------------------------------------------

class TestExtractComponents:
    """Test component extraction from generated code."""

    def test_extract_buttons(self, generator):
        code = '<button class="btn">Submit</button><button>Cancel</button>'
        comps = generator._extract_components(code)
        buttons = [c for c in comps if c.type == "button"]
        assert len(buttons) == 2
        assert buttons[0].properties["text"] == "Submit"
        assert buttons[1].properties["text"] == "Cancel"

    def test_extract_form(self, generator):
        code = '<form><input type="email"><input type="password"></form>'
        comps = generator._extract_components(code)
        forms = [c for c in comps if c.type == "form"]
        assert len(forms) == 1
        assert "email" in forms[0].properties["fields"]
        assert "password" in forms[0].properties["fields"]

    def test_extract_table(self, generator):
        code = '<table><thead><tr><th>Name</th><th>Email</th></tr></thead></table>'
        comps = generator._extract_components(code)
        tables = [c for c in comps if c.type == "table"]
        assert len(tables) == 1
        assert tables[0].properties["columns"] == ["Name", "Email"]

    def test_extract_nav(self, generator):
        code = '<div class="sidebar"><a class="nav-item">Home</a><a class="nav-item">Settings</a></div>'
        comps = generator._extract_components(code)
        navs = [c for c in comps if c.type == "nav"]
        assert len(navs) == 1
        assert "Home" in navs[0].properties["items"]

    def test_extract_modal(self, generator):
        code = '<div class="modal"><div class="modal-body">Content</div></div>'
        comps = generator._extract_components(code)
        modals = [c for c in comps if c.type == "modal"]
        assert len(modals) == 1

    def test_extract_cards(self, generator):
        code = '<div class="card">A</div><div class="card">B</div>'
        comps = generator._extract_components(code)
        cards = [c for c in comps if c.type == "card"]
        assert len(cards) == 1
        assert cards[0].properties["count"] == 2

    def test_empty_code_returns_no_components(self, generator):
        assert generator._extract_components("") == []


# ---------------------------------------------------------------------------
# TestImageAnalysis
# ---------------------------------------------------------------------------

class TestImageAnalysis:
    """Test image path analysis for description hints."""

    def test_extracts_from_filename(self, tmp_cwd):
        img = Path(tmp_cwd) / "login-form-mockup.png"
        img.write_bytes(b"\x89PNG\r\n")  # Minimal PNG header
        gen = ScreenshotToCode(cwd=tmp_cwd)
        desc = gen._analyze_image(str(img))
        assert "login" in desc
        assert "form" in desc

    def test_missing_file_returns_empty(self, generator):
        desc = generator._analyze_image("/nonexistent/file.png")
        assert desc == ""


# ---------------------------------------------------------------------------
# TestGeneratePreview
# ---------------------------------------------------------------------------

class TestGeneratePreview:
    """Test preview HTML generation."""

    def test_html_preview_is_code_itself(self, generator):
        html = "<!DOCTYPE html><html></html>"
        preview = generator._generate_preview(html, "html")
        assert preview == html

    def test_react_preview_wraps_in_html(self, generator):
        code = "export default function App() {}"
        preview = generator._generate_preview(code, "react")
        assert "<!DOCTYPE html>" in preview
        assert "React" in preview


# ---------------------------------------------------------------------------
# TestFormatOutput
# ---------------------------------------------------------------------------

class TestFormatOutput:

    def test_format_includes_framework(self):
        result = GeneratedUI(
            framework="html",
            code="<div>Hello</div>",
            components=[UIComponent(name="Div", type="card", properties={"count": 1})],
        )
        output = format_generated_ui(result)
        assert "Framework: html" in output
        assert "Components: 1" in output

    def test_format_includes_warnings(self):
        result = GeneratedUI(
            framework="html",
            code="<div></div>",
            warnings=["Something happened"],
        )
        output = format_generated_ui(result)
        assert "Warning: Something happened" in output


# ---------------------------------------------------------------------------
# TestEndToEnd
# ---------------------------------------------------------------------------

class TestEndToEnd:
    """Integration-style tests for the full generate flow."""

    def test_generate_with_image_path(self, tmp_cwd):
        img = Path(tmp_cwd) / "dashboard-overview.png"
        img.write_bytes(b"\x89PNG\r\n")
        gen = ScreenshotToCode(cwd=tmp_cwd)
        result = gen.generate(image_path=str(img), framework="html")
        assert result.framework == "html"
        assert "<!DOCTYPE html>" in result.code

    def test_generate_with_description_only(self, tmp_cwd):
        gen = ScreenshotToCode(cwd=tmp_cwd)
        result = gen.generate(description="login form")
        assert result.framework == "html"
        assert "<form" in result.code

    def test_generate_with_unsupported_framework(self, tmp_cwd):
        gen = ScreenshotToCode(cwd=tmp_cwd)
        result = gen.generate(description="login", framework="angular")
        assert result.framework == "html"  # Falls back
        assert any("Unsupported" in w for w in result.warnings)

    def test_generate_no_input_defaults(self, tmp_cwd):
        gen = ScreenshotToCode(cwd=tmp_cwd)
        result = gen.generate()
        assert result.code  # Should produce something
        assert len(result.warnings) > 0  # Should warn about defaults

    def test_output_file(self, tmp_cwd):
        """Test the CLI output path by calling generate and writing."""
        gen = ScreenshotToCode(cwd=tmp_cwd)
        result = gen.generate(description="login form", framework="html")
        out = Path(tmp_cwd) / "output.html"
        out.write_text(result.code)
        assert out.exists()
        assert "<!DOCTYPE html>" in out.read_text()
