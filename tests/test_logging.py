"""Logging behaviour: library-grade defaults per the Python logging HOWTO."""

import ast
import io
import logging
import pathlib

import vsdx
from vsdx import VisioFile

BASE = "test8_simple_connector.vsdx"

_LOG_METHODS = frozenset({"debug", "info", "warning", "warn", "error", "exception", "critical", "fatal", "log"})

# How many log calls the package has. Asserted, because a walk that matched
# nothing would pass with an empty offender list and report a contract it had
# not checked - which is the failure this whole commit is about. Raise it when
# you add logging; if it has gone down, say why in the commit.
_LOG_CALLS_IN_THE_PACKAGE = 19


def _is_logger(node: ast.expr) -> bool:
    """Whether the receiver of the call is something named like a logger.

    By name, because an AST has no runtime objects to ask. Every call site in
    the package goes through a module-level `logger`; `getLogger(...).debug(...)`
    is matched too, because that is how a call escapes the convention.
    """
    if isinstance(node, ast.Call):
        func = node.func
        return isinstance(func, (ast.Name, ast.Attribute)) and _called_name(func) == "getlogger"
    return _called_name(node).endswith(("logger", "log"))


def _called_name(node: ast.expr) -> str:
    name = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else ""
    return name.lower()


def _is_eagerly_formatted(message: ast.expr | None) -> bool:
    """Whether the message argument does its own interpolation.

    An f-string, a `%` expression, a `+` concatenation, or a `.format()` call:
    all four are evaluated on the way in, whatever the level is set to.
    """
    if isinstance(message, ast.JoinedStr):
        return True
    if isinstance(message, ast.BinOp) and isinstance(message.op, (ast.Mod, ast.Add)):
        return True
    return isinstance(message, ast.Call) and isinstance(message.func, ast.Attribute) and message.func.attr == "format"


def test_no_output_on_default_configuration(vsdx_copy, capsys):
    """Default config: NullHandler only; nothing reaches stdout/stderr."""
    path = vsdx_copy(BASE)
    with VisioFile(path) as vis:
        vis.pages[0].delete_shape(vis.pages[0].all_shapes[0])
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_debug_true_bridges_to_logging(vsdx_copy, capsys):
    """debug=True reproduces the old print behaviour via a logging handler."""
    path = vsdx_copy(BASE)
    with VisioFile(path, debug=True) as vis:
        vis.pages[0]  # touch enough to trigger debug paths
    # handler writes to stderr; capsys captures it even though it is
    # bypassing print (StreamHandler holds the stream by default capture)
    err = capsys.readouterr().err
    assert "vsdx.vsdxfile" in err


def test_host_application_can_capture_module_logs(vsdx_copy):
    """A host app configures the 'vsdx' logger and receives module records."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    root = logging.getLogger("vsdx")
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        path = vsdx_copy(BASE)
        with VisioFile(path) as vis:
            vis.remove_page_by_index(0)
        assert "_remove_page_from_app_xml()" in stream.getvalue()
        assert "VisioFile(filename=" in stream.getvalue()
    finally:
        root.removeHandler(handler)
        root.setLevel(logging.NOTSET)


def test_no_log_call_in_the_package_formats_its_own_message():
    """Every call passes a format string and its arguments, per the logging HOWTO.

    A disabled level is the common case, because the default handler is a
    NullHandler, and an f-string is interpolated before `debug` is entered: the
    work is done and thrown away.

    This is read off the source because the property belongs to the call sites.
    The test it replaces called `logging` itself with no library code in
    between, and so held whatever the library did.

    What it does not see is an expensive *argument*: `logger.debug("%s", f(x))`
    calls `f` at any level, and four calls in `vsdxfile.py` pass
    `pretty_print_element` of a page part that way. Lazy formatting is not lazy
    evaluation, and no reading of the message argument can tell you otherwise.
    """
    offenders = []
    inspected = 0
    for path in sorted(pathlib.Path(vsdx.__file__).parent.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in _LOG_METHODS or not _is_logger(node.func.value):
                continue
            inspected += 1
            # `logger.log(level, msg, ...)` puts the message second
            message = node.args[1] if node.func.attr == "log" and len(node.args) > 1 else (node.args[0] if node.args else None)
            if _is_eagerly_formatted(message):
                offenders.append(f"{path.name}:{node.lineno}")

    assert inspected == _LOG_CALLS_IN_THE_PACKAGE, (
        f"found {inspected} log calls, expected {_LOG_CALLS_IN_THE_PACKAGE}. If logging was added or "
        "removed, update the count; if it dropped to zero, `_is_logger` has stopped recognising the "
        "call sites and this test is passing without checking anything."
    )
    assert offenders == [], (
        "these log calls build their message before the logging module decides whether to emit it: "
        + ", ".join(offenders)
        + ". Pass a %s format string and the values as arguments instead."
    )


def test_package_root_has_null_handler_only():
    """Library contract: the 'vsdx' logger carries a NullHandler and no
    propagation-escaping handlers of other kinds by default."""
    root = logging.getLogger("vsdx")
    vsdx_handlers = [h for h in root.handlers if not getattr(h, "_vsdx_debug_handler", False)]
    assert len(vsdx_handlers) == 1
    assert isinstance(vsdx_handlers[0], logging.NullHandler)
