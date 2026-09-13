"""Package expansion limits: hostile and accidental archives are rejected before load."""

import json
import os
import shutil
import warnings
import zipfile

import pytest
from helpers.broken_package import append_member, understated

import vsdxkit
from vsdxkit.package import PackageLimits, _read_bounded, read_archive_members

# Every test here builds a package designed to be wrong - padding members to
# trip a count cap, names that escape the archive, payloads that expand out of
# all proportion. The structural validator would report all of it, correctly
# and uselessly.
pytestmark = pytest.mark.allow_invalid_package

FIXTURES = os.path.dirname(os.path.realpath(__file__))

LIMITS_FILENAME = "vsdxkit.limits.json"


def _copy(name: str, tmp_path) -> str:
    destination = os.path.join(str(tmp_path), name)
    shutil.copy(os.path.join(FIXTURES, name), destination)
    return destination


def _limits_path(tmp_path) -> str:
    return os.path.join(str(tmp_path), LIMITS_FILENAME)


def _write_limits(tmp_path, limits: dict) -> str:
    path = _limits_path(tmp_path)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(limits, handle)
    return path


def test_default_limits_accept_real_documents(tmp_path):
    path = _copy("test1.vsdx", tmp_path)
    with vsdxkit.VisioFile(path) as visio:
        assert visio.file_open


def test_default_compression_ratio_guard_rejects_highly_compressible_payload(tmp_path):
    path = _copy("test1.vsdx", tmp_path)
    append_member(path, "visio/pages/pad.bin", b"\0" * 500_000)
    with pytest.raises(vsdxkit.PackageLimitError) as excinfo:
        vsdxkit.VisioFile(path)
    assert excinfo.value.reason == "compression_ratio"


def test_per_member_size_limit(tmp_path):
    path = _copy("test1.vsdx", tmp_path)
    append_member(path, "visio/pages/pad.bin", os.urandom(20_000))  # incompressible
    limits_path = _write_limits(tmp_path, {"max_member_size": 10_000})
    with pytest.raises(vsdxkit.PackageLimitError) as excinfo:
        vsdxkit.VisioFile(path, limits_path=limits_path)
    assert excinfo.value.reason == "member_size"


def test_total_uncompressed_size_limit(tmp_path):
    path = _copy("test1.vsdx", tmp_path)
    append_member(path, "visio/pages/pad.bin", os.urandom(20_000))  # incompressible
    limits_path = _write_limits(tmp_path, {"max_total_uncompressed": 60_000})
    with pytest.raises(vsdxkit.PackageLimitError) as excinfo:
        vsdxkit.VisioFile(path, limits_path=limits_path)
    assert excinfo.value.reason == "total_size"


def test_member_count_limit(tmp_path):
    path = _copy("test1.vsdx", tmp_path)
    for index in range(25):
        append_member(path, f"visio/pages/pad{index}.bin", b"pad")
    limits_path = _write_limits(tmp_path, {"max_members": 20})
    with pytest.raises(vsdxkit.PackageLimitError) as excinfo:
        vsdxkit.VisioFile(path, limits_path=limits_path)
    assert excinfo.value.reason == "member_count"


def test_per_member_limit_is_enforced_before_total(tmp_path):
    path = _copy("test1.vsdx", tmp_path)
    append_member(path, "visio/pages/pad.bin", os.urandom(20_000))  # incompressible
    limits_path = _write_limits(tmp_path, {"max_member_size": 10_000, "max_total_uncompressed": 15_000})
    with pytest.raises(vsdxkit.PackageLimitError) as excinfo:
        vsdxkit.VisioFile(path, limits_path=limits_path)
    assert excinfo.value.reason == "member_size"


def test_duplicate_member_name_rejected(tmp_path):
    path = _copy("test1.vsdx", tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        append_member(path, "visio/document.xml", b"<xml/>")
    with pytest.raises(vsdxkit.PackageLimitError) as excinfo:
        vsdxkit.VisioFile(path)
    assert excinfo.value.reason == "duplicate_member"


@pytest.mark.parametrize("name", ["..\\evil.bin", "a/../../evil.bin", "/abs/evil.bin"])
def test_suspicious_member_name_rejected(tmp_path, name):
    path = _copy("test1.vsdx", tmp_path)
    append_member(path, name, b"evil")
    with pytest.raises(vsdxkit.PackageLimitError) as excinfo:
        vsdxkit.VisioFile(path)
    assert excinfo.value.reason == "member_name"


def test_explicit_limits_relax_caps_for_trusted_documents(tmp_path):
    path = _copy("test1.vsdx", tmp_path)
    append_member(path, "visio/pages/pad.bin", os.urandom(20_000))  # incompressible
    limits_path = _write_limits(
        tmp_path,
        {"max_member_size": 1_048_576, "max_total_uncompressed": 4_194_304, "max_ratio": 1_000},
    )
    with vsdxkit.VisioFile(path, limits_path=limits_path) as visio:
        assert visio.file_open


def test_non_finite_limit_values_are_rejected(tmp_path):
    cases: dict[str, float] = {
        "max_members": float("nan"),
        "max_member_size": float("inf"),
        "max_total_uncompressed": float("nan"),
        "max_ratio": float("inf"),
    }
    for name, value in cases.items():
        with pytest.raises(ValueError, match="finite"):
            PackageLimits(**{name: value})


def test_non_finite_json_limits_are_a_package_limit_error(tmp_path):
    path = _copy("test1.vsdx", tmp_path)
    limits_path = os.path.join(str(tmp_path), "nan.json")
    with open(limits_path, "w", encoding="utf-8") as handle:
        handle.write('{"max_members": NaN}')
    with pytest.raises(vsdxkit.PackageLimitError) as excinfo:
        vsdxkit.VisioFile(path, limits_path=limits_path)
    assert excinfo.value.reason == "limits_file"


def test_directory_entries_count_toward_member_limit(tmp_path):
    path = _copy("test1.vsdx", tmp_path)
    with zipfile.ZipFile(path, "a") as archive:
        for index in range(30):
            archive.writestr(f"d{index}/", b"")
    limits_path = _write_limits(tmp_path, {"max_members": 20})
    with pytest.raises(vsdxkit.PackageLimitError) as excinfo:
        vsdxkit.VisioFile(path, limits_path=limits_path)
    assert excinfo.value.reason == "member_count"


def test_missing_limits_file_is_a_package_limit_error(tmp_path):
    path = _copy("test1.vsdx", tmp_path)
    limits_path = os.path.join(str(tmp_path), "nonexistent.json")
    with pytest.raises(vsdxkit.PackageLimitError) as excinfo:
        vsdxkit.VisioFile(path, limits_path=limits_path)
    assert excinfo.value.reason == "limits_file"


def test_unparsable_limits_file_is_a_package_limit_error(tmp_path):
    path = _copy("test1.vsdx", tmp_path)
    limits_path = os.path.join(str(tmp_path), "broken.json")
    with open(limits_path, "w", encoding="utf-8") as handle:
        handle.write("{not json")
    with pytest.raises(vsdxkit.PackageLimitError) as excinfo:
        vsdxkit.VisioFile(path, limits_path=limits_path)
    assert excinfo.value.reason == "limits_file"


def test_unknown_limits_keys_are_rejected(tmp_path):
    path = _copy("test1.vsdx", tmp_path)
    limits_path = _write_limits(tmp_path, {"max_membres": 10})
    with pytest.raises(vsdxkit.PackageLimitError) as excinfo:
        vsdxkit.VisioFile(path, limits_path=limits_path)
    assert excinfo.value.reason == "limits_file"


def test_streaming_counter_rejects_over_delivery():
    """A reader that returns more bytes than declared must trip the counter."""

    class LyingReader:
        def read(self, size: int = -1, /) -> bytes:
            return b"y" * (size + 1)

    with pytest.raises(vsdxkit.PackageLimitError) as excinfo:
        _read_bounded(LyingReader(), 10, "pad.bin", PackageLimits(max_member_size=5))
    assert excinfo.value.reason == "member_size"


def test_error_message_names_the_limit_and_values(tmp_path):
    path = _copy("test1.vsdx", tmp_path)
    append_member(path, "visio/pages/pad.bin", os.urandom(20_000))  # incompressible
    limits_path = _write_limits(tmp_path, {"max_total_uncompressed": 60_000})
    with pytest.raises(vsdxkit.PackageLimitError) as excinfo:
        vsdxkit.VisioFile(path, limits_path=limits_path)
    assert "60000" in str(excinfo.value)


# The uncompressed-size cap is applied to `info.file_size`, which the archive
# declares and an attacker therefore chooses. The two tests below are why that
# is sound rather than a hole: `ZipFile` refuses to hand back more of a member
# than the member claims to hold, so a lie can only ever make the loader
# materialise *less*. `_read_bounded` is the second line, for a reader that is
# not `ZipFile` at all (`test_streaming_counter_rejects_over_delivery`).
#
# This is a dependency on CPython's behaviour, not on ours, which is exactly
# why it is pinned here: if a future release started honouring the compressed
# stream over the declared size, the total cap would quietly stop bounding
# anything and nothing else in this suite would notice.
UNDERSTATED_PAYLOAD = bytes(range(256)) * 64


def test_a_member_that_understates_its_size_is_refused(tmp_path):
    """`ZipFile` fails the CRC; the loader reports it as a malformed package.

    The `BadZipFile` this used to raise is still the cause, and it is still
    CPython's refusal that does the work: the type is what changed.
    """
    path = understated(os.path.join(str(tmp_path), "understated.vsdx"), "visio/pages/pad.bin", UNDERSTATED_PAYLOAD, 1)
    with pytest.raises(vsdxkit.MalformedPackageError) as excinfo:
        read_archive_members(path, PackageLimits())
    assert isinstance(excinfo.value.__cause__, zipfile.BadZipFile)


def test_a_member_cannot_deliver_more_bytes_than_it_declares(tmp_path):
    """The stronger case: the CRC agrees with the lie, so nothing raises."""
    path = understated(
        os.path.join(str(tmp_path), "understated.vsdx"),
        "visio/pages/pad.bin",
        UNDERSTATED_PAYLOAD,
        1,
        consistent_crc=True,
    )
    ((_, delivered),) = read_archive_members(path, PackageLimits())
    assert len(delivered) == 1
