"""Tests for jacoco_parser.py — JaCoCo XML coverage report parser."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from code_agents.cicd.jacoco_parser import (
    ClassCoverage,
    CoverageReport,
    parse_jacoco_xml,
    find_jacoco_xml,
    get_uncovered_methods,
    format_coverage_report,
    coverage_meets_threshold,
)


# ── ClassCoverage dataclass ──────────────────────────────────────────


class TestClassCoverage:
    def test_defaults(self):
        cc = ClassCoverage(name="MyClass")
        assert cc.package == ""
        assert cc.line_covered == 0
        assert cc.line_missed == 0
        assert cc.branch_covered == 0
        assert cc.branch_missed == 0
        assert cc.method_covered == 0
        assert cc.method_missed == 0

    def test_line_total(self):
        cc = ClassCoverage(name="C", line_covered=80, line_missed=20)
        assert cc.line_total == 100

    def test_line_pct(self):
        cc = ClassCoverage(name="C", line_covered=80, line_missed=20)
        assert cc.line_pct == 80.0

    def test_line_pct_zero_total(self):
        cc = ClassCoverage(name="C")
        assert cc.line_pct == 0.0

    def test_branch_pct(self):
        cc = ClassCoverage(name="C", branch_covered=15, branch_missed=5)
        assert cc.branch_pct == 75.0

    def test_branch_pct_zero_total(self):
        cc = ClassCoverage(name="C")
        assert cc.branch_pct == 0.0

    def test_full_name_with_package(self):
        cc = ClassCoverage(name="MyClass", package="com.example")
        assert cc.full_name == "com.example.MyClass"

    def test_full_name_no_package(self):
        cc = ClassCoverage(name="MyClass")
        assert cc.full_name == "MyClass"


# ── CoverageReport dataclass ────────────────────────────────────────


class TestCoverageReport:
    def test_defaults(self):
        r = CoverageReport()
        assert r.classes == []
        assert r.total_line_covered == 0
        assert r.total_line_missed == 0

    def test_line_pct(self):
        r = CoverageReport(total_line_covered=75, total_line_missed=25)
        assert r.line_pct == 75.0

    def test_line_pct_zero(self):
        r = CoverageReport()
        assert r.line_pct == 0.0

    def test_branch_pct(self):
        r = CoverageReport(total_branch_covered=60, total_branch_missed=40)
        assert r.branch_pct == 60.0

    def test_branch_pct_zero(self):
        r = CoverageReport()
        assert r.branch_pct == 0.0

    def test_class_count(self):
        r = CoverageReport(classes=[ClassCoverage(name="A"), ClassCoverage(name="B")])
        assert r.class_count == 2


# ── parse_jacoco_xml ─────────────────────────────────────────────────


SAMPLE_JACOCO_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE report PUBLIC "-//JACOCO//DTD Report 1.1//EN" "report.dtd">
<report name="test-report">
  <package name="com/example/service">
    <class name="com/example/service/UserService">
      <counter type="LINE" missed="10" covered="90"/>
      <counter type="BRANCH" missed="5" covered="15"/>
      <counter type="METHOD" missed="2" covered="8"/>
    </class>
    <class name="com/example/service/OrderService">
      <counter type="LINE" missed="40" covered="60"/>
      <counter type="BRANCH" missed="20" covered="10"/>
      <counter type="METHOD" missed="5" covered="5"/>
    </class>
  </package>
  <package name="com/example/controller">
    <class name="com/example/controller/UserController">
      <counter type="LINE" missed="5" covered="45"/>
      <counter type="BRANCH" missed="2" covered="8"/>
      <counter type="METHOD" missed="1" covered="4"/>
    </class>
  </package>
  <counter type="LINE" missed="55" covered="195"/>
  <counter type="BRANCH" missed="27" covered="33"/>
</report>
"""


class TestParseJacocoXml:
    def test_parse_valid(self, tmp_path):
        xml_file = tmp_path / "jacoco.xml"
        xml_file.write_text(SAMPLE_JACOCO_XML)
        report = parse_jacoco_xml(str(xml_file))
        assert report is not None
        assert report.class_count == 3
        assert report.total_line_covered == 195
        assert report.total_line_missed == 55
        assert report.total_branch_covered == 33
        assert report.total_branch_missed == 27

    def test_parse_class_details(self, tmp_path):
        xml_file = tmp_path / "jacoco.xml"
        xml_file.write_text(SAMPLE_JACOCO_XML)
        report = parse_jacoco_xml(str(xml_file))
        # Classes sorted by line_pct ascending (worst first)
        assert report.classes[0].name == "OrderService"
        assert report.classes[0].package == "com.example.service"
        assert report.classes[0].line_covered == 60
        assert report.classes[0].line_missed == 40

    def test_parse_missing_file(self, tmp_path):
        result = parse_jacoco_xml(str(tmp_path / "missing.xml"))
        assert result is None

    def test_parse_invalid_xml(self, tmp_path):
        xml_file = tmp_path / "bad.xml"
        xml_file.write_text("not xml content <<>")
        result = parse_jacoco_xml(str(xml_file))
        assert result is None

    def test_sorted_by_coverage(self, tmp_path):
        xml_file = tmp_path / "jacoco.xml"
        xml_file.write_text(SAMPLE_JACOCO_XML)
        report = parse_jacoco_xml(str(xml_file))
        pcts = [c.line_pct for c in report.classes]
        assert pcts == sorted(pcts)


# ── find_jacoco_xml ──────────────────────────────────────────────────


class TestFindJacocoXml:
    def test_maven_location(self, tmp_path):
        maven_path = tmp_path / "target" / "site" / "jacoco" / "jacoco.xml"
        maven_path.parent.mkdir(parents=True)
        maven_path.write_text("<report></report>")
        result = find_jacoco_xml(str(tmp_path))
        assert result == str(maven_path)

    def test_gradle_location(self, tmp_path):
        gradle_path = tmp_path / "build" / "reports" / "jacoco" / "test" / "jacocoTestReport.xml"
        gradle_path.parent.mkdir(parents=True)
        gradle_path.write_text("<report></report>")
        result = find_jacoco_xml(str(tmp_path))
        assert result == str(gradle_path)

    def test_not_found(self, tmp_path):
        result = find_jacoco_xml(str(tmp_path))
        assert result is None

    def test_recursive_search(self, tmp_path):
        nested = tmp_path / "modules" / "api" / "build" / "reports" / "jacoco_report.xml"
        nested.parent.mkdir(parents=True)
        nested.write_text("<report></report>")
        result = find_jacoco_xml(str(tmp_path))
        assert result == str(nested)


# ── get_uncovered_methods ────────────────────────────────────────────


class TestGetUncoveredMethods:
    def test_below_threshold(self):
        report = CoverageReport(classes=[
            ClassCoverage(name="Bad", package="pkg", line_covered=50, line_missed=50),
            ClassCoverage(name="Good", package="pkg", line_covered=90, line_missed=10),
        ])
        below = get_uncovered_methods(report, threshold=80.0)
        assert len(below) == 1
        assert below[0]["class"] == "pkg.Bad"
        assert below[0]["line_pct"] == 50.0
        assert below[0]["lines_to_cover"] == 50

    def test_all_above_threshold(self):
        report = CoverageReport(classes=[
            ClassCoverage(name="A", line_covered=85, line_missed=15),
        ])
        below = get_uncovered_methods(report, threshold=80.0)
        assert len(below) == 0

    def test_skips_zero_total(self):
        report = CoverageReport(classes=[
            ClassCoverage(name="Empty"),
        ])
        below = get_uncovered_methods(report, threshold=80.0)
        assert len(below) == 0


# ── format_coverage_report ───────────────────────────────────────────


class TestFormatCoverageReport:
    def test_format_with_data(self):
        report = CoverageReport(
            classes=[
                ClassCoverage(name="A", package="pkg", line_covered=90, line_missed=10,
                              branch_covered=8, branch_missed=2),
                ClassCoverage(name="B", package="pkg", line_covered=50, line_missed=50,
                              branch_covered=5, branch_missed=5),
            ],
            total_line_covered=140,
            total_line_missed=60,
            total_branch_covered=13,
            total_branch_missed=7,
        )
        output = format_coverage_report(report, threshold=80.0)
        assert "Overall:" in output
        assert "70.0%" in output  # 140/(140+60)
        assert "pkg.A" in output
        assert "pkg.B" in output
        assert "Below 80.0%: 1 classes" in output

    def test_format_none(self):
        output = format_coverage_report(None)
        assert "No coverage data" in output

    def test_format_empty_report(self):
        report = CoverageReport()
        output = format_coverage_report(report)
        assert "Overall:" in output
        assert "0.0%" in output


# ── coverage_meets_threshold ─────────────────────────────────────────


class TestCoverageMeetsThreshold:
    def test_above_threshold(self):
        report = CoverageReport(total_line_covered=85, total_line_missed=15)
        assert coverage_meets_threshold(report, 80.0) is True

    def test_below_threshold(self):
        report = CoverageReport(total_line_covered=70, total_line_missed=30)
        assert coverage_meets_threshold(report, 80.0) is False

    def test_exact_threshold(self):
        report = CoverageReport(total_line_covered=80, total_line_missed=20)
        assert coverage_meets_threshold(report, 80.0) is True
