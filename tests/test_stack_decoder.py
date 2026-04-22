"""Tests for the StackDecoder module."""

import pytest
from code_agents.observability.stack_decoder import StackDecoder, StackDecodeConfig, StackDecodeResult, format_stack_decode


class TestStackDecoder:
    def test_detect_python(self):
        decoder = StackDecoder(StackDecodeConfig())
        assert decoder._detect_language('Traceback (most recent call last):') == "python"

    def test_detect_java(self):
        decoder = StackDecoder(StackDecodeConfig())
        assert decoder._detect_language('  at com.foo.Bar(Bar.java:42)') == "java"

    def test_detect_go(self):
        decoder = StackDecoder(StackDecodeConfig())
        assert decoder._detect_language('goroutine 1 [running]:\nmain.go:42') == "go"

    def test_parse_python_trace(self):
        trace = '''Traceback (most recent call last):
  File "app.py", line 10, in main
    result = process(data)
  File "app.py", line 20, in process
    return data["key"]
KeyError: 'key'
'''
        decoder = StackDecoder(StackDecodeConfig())
        result = decoder.decode(trace)
        assert result.language == "python"
        assert result.error_type == "KeyError"
        assert result.error_message == "'key'"
        assert len(result.frames) == 2
        assert result.frames[0].file == "app.py"
        assert result.frames[0].line == 10
        assert result.frames[1].function == "process"

    def test_parse_java_trace(self):
        trace = '''NullPointerException: null
  at com.app.Service.process(Service.java:42)
  at com.app.Controller.handle(Controller.java:15)
'''
        decoder = StackDecoder(StackDecodeConfig())
        result = decoder.decode(trace)
        assert result.language == "java"
        assert result.error_type == "NullPointerException"
        assert len(result.frames) == 2

    def test_explain_common_errors(self):
        trace = '''Traceback (most recent call last):
  File "app.py", line 5, in main
    x.foo()
AttributeError: 'NoneType' object has no attribute 'foo'
'''
        decoder = StackDecoder(StackDecodeConfig())
        result = decoder.decode(trace)
        assert "attribute" in result.explanation.lower() or "none" in result.explanation.lower()
        assert result.suggested_fix != ""

    def test_resolve_local_files(self, tmp_path):
        (tmp_path / "app.py").write_text("x = 1\n")
        trace = '''Traceback (most recent call last):
  File "app.py", line 1, in <module>
    x = 1
ValueError: invalid
'''
        decoder = StackDecoder(StackDecodeConfig(cwd=str(tmp_path)))
        result = decoder.decode(trace)
        assert any(f.is_local for f in result.frames)

    def test_format_output(self):
        result = StackDecodeResult(
            language="python", error_type="KeyError", error_message="'name'",
            explanation="Dict key missing", suggested_fix="Use .get()",
        )
        output = format_stack_decode(result)
        assert "KeyError" in output
        assert "python" in output
