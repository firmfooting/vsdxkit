"""The lint job's workflow pin checks.

`check_action_pins.py` resolves action digests over the network, so only its
offline half is covered here: the rule that every `astral-sh/setup-uv` step
pins a uv version, and that they all pin the same one. That pin is a `with:`
input, which nothing else in the repository reads -- not the digest check
beside it, not Renovate's `python-deps` rule -- so nothing but this compares
the copies of the version string.

Every case is built in tmp_path. Reading `.github/workflows/` instead would
turn these tests red the next time someone adds a workflow, which says nothing
about whether the checker works.
"""

import importlib.util
import os

import pytest

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "tools")

spec = importlib.util.spec_from_file_location("check_action_pins", os.path.join(TOOLS, "check_action_pins.py"))
check_action_pins = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_action_pins)

DIGEST = "bec219d24cd3e171d82865faccec33120bb574f4"

# The unnamed spelling: `uses:` sits on the dash line.
BARE_STEP = f"""\
jobs:
  build:
    steps:
      - uses: astral-sh/setup-uv@{DIGEST}  # v10.1.0
        with:
          enable-cache: false
          version: "0.12.7"
      - run: uv sync --locked
"""

# The named spelling: `uses:` is a sibling key one line down. An earlier
# revision of the check matched only the dash line and skipped this entirely.
NAMED_STEP = f"""\
jobs:
  build:
    steps:
      - name: Install uv
        uses: astral-sh/setup-uv@{DIGEST}  # v10.1.0
        with:
          enable-cache: false
          version: "0.12.7"
      - run: uv sync --locked
"""


def write(directory, name, content):
    (directory / name).write_text(content, encoding="utf-8")
    return directory


def test_matching_pins_pass_and_the_summary_names_them(tmp_path):
    write(tmp_path, "a.yml", BARE_STEP)
    write(tmp_path, "b.yml", NAMED_STEP)
    failures, summary = check_action_pins.uv_pin_failures(tmp_path)
    assert failures == []
    assert "2 setup-uv steps" in summary
    assert "0.12.7" in summary


@pytest.mark.parametrize("template", [BARE_STEP, NAMED_STEP], ids=["bare", "named"])
def test_a_step_with_no_version_input_is_reported(tmp_path, template):
    """Both spellings must be caught: an unpinned step runs whatever uv is current."""
    write(tmp_path, "ci.yml", template.replace('          version: "0.12.7"\n', ""))
    failures, _ = check_action_pins.uv_pin_failures(tmp_path)
    assert len(failures) == 1
    assert "ci.yml" in failures[0]
    assert "no `version:`" in failures[0]


def test_disagreeing_pins_report_both_versions_and_where_they_are(tmp_path):
    write(tmp_path, "ci.yml", BARE_STEP)
    write(tmp_path, "zizmor.yml", BARE_STEP.replace("0.12.7", "0.11.0"))
    failures, _ = check_action_pins.uv_pin_failures(tmp_path)
    assert len(failures) == 1
    reported = failures[0]
    assert "0.11.0" in reported and "0.12.7" in reported
    assert "ci.yml" in reported and "zizmor.yml" in reported


def test_a_workflow_directory_with_no_setup_uv_steps_does_not_read_as_a_pass(tmp_path):
    """Zero steps checked and eight steps checked must not print the same line."""
    write(tmp_path, "pr-title.yml", "jobs:\n  title:\n    steps:\n      - run: echo hello\n")
    failures, summary = check_action_pins.uv_pin_failures(tmp_path)
    assert failures == []
    assert summary.startswith("0 setup-uv steps")


def test_python_version_does_not_satisfy_the_uv_pin(tmp_path):
    """setup-uv takes a `python-version:` input too, and it pins the wrong thing."""
    write(
        tmp_path,
        "ci.yml",
        f"""\
jobs:
  build:
    steps:
      - uses: astral-sh/setup-uv@{DIGEST}  # v10.1.0
        with:
          enable-cache: false
          python-version: "3.12"
      - run: uv sync --locked
""",
    )
    failures, _ = check_action_pins.uv_pin_failures(tmp_path)
    assert len(failures) == 1
    assert "no `version:`" in failures[0]


def test_the_pin_is_read_from_the_step_it_belongs_to(tmp_path):
    """A later step's `version:` must not be borrowed by an unpinned one above it."""
    write(
        tmp_path,
        "ci.yml",
        f"""\
jobs:
  build:
    steps:
      - uses: astral-sh/setup-uv@{DIGEST}  # v10.1.0
        with:
          enable-cache: false
      - name: Something else
        uses: some/other-action@{DIGEST}  # v1
        with:
          version: "0.12.7"
""",
    )
    failures, _ = check_action_pins.uv_pin_failures(tmp_path)
    assert len(failures) == 1
    assert "no `version:`" in failures[0]
