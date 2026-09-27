"""Packaging invariants: manifest.json, hacs.json and the brand assets.

These files are never exercised by the integration's own code paths, so nothing
else notices when they drift out of sync with each other or with the domain.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

INTEGRATION_DIR = Path("custom_components") / "smartsolar_ha"
MANIFEST = json.loads((INTEGRATION_DIR / "manifest.json").read_text(encoding="utf-8"))

# Brand images Home Assistant serves from custom_components/<domain>/brand/.
# See homeassistant/components/brands/const.py:ALLOWED_IMAGES and
# loader.Integration.has_branding — the FOLDER is what enables local branding.
BRAND_IMAGES = ("icon.png", "icon@2x.png", "logo.png")


def _png_size(path: Path) -> tuple[int, int]:
    """Read width/height straight out of the PNG IHDR chunk."""
    header = path.read_bytes()[:24]
    assert header[:8] == b"\x89PNG\r\n\x1a\n", f"{path} is not a PNG"
    width, height = struct.unpack(">II", header[16:24])
    return width, height


class TestManifest:
    def test_domain_matches_the_folder_name(self):
        """HA resolves an integration as custom_components/<domain>/manifest.json."""
        assert MANIFEST["domain"] == INTEGRATION_DIR.name

    def test_required_keys_are_present(self):
        for key in ("domain", "name", "version", "documentation", "issue_tracker", "codeowners", "config_flow"):
            assert MANIFEST.get(key), f"manifest.json is missing {key}"

    def test_version_matches_const_and_pyproject(self):
        """A stale sw_version is how a live instance ended up running old code."""
        from custom_components.smartsolar_ha.const import VERSION

        assert MANIFEST["version"] == VERSION

        pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
        assert f'version = "{VERSION}"' in pyproject

    def test_no_branding_key(self):
        """``brand`` is NOT a Home Assistant manifest key.

        Home Assistant serves local brand images from
        ``custom_components/<domain>/brand/`` (``loader.Integration.has_branding``
        checks that folder). A ``brand`` manifest block is silently ignored, so
        it can only ever look like branding that is configured when it is not.
        """
        assert "brand" not in MANIFEST


class TestBrandAssets:
    def test_brand_directory_exists(self):
        """Without this folder Home Assistant ignores the local brand images."""
        assert (INTEGRATION_DIR / "brand").is_dir()

    @pytest.mark.parametrize("image", BRAND_IMAGES)
    def test_brand_image_is_a_valid_png(self, image):
        assert _png_size(INTEGRATION_DIR / "brand" / image) != (0, 0)

    @pytest.mark.parametrize(("image", "size"), [("icon.png", 256), ("icon@2x.png", 512), ("logo.png", 512)])
    def test_brand_image_has_the_expected_size(self, image, size):
        assert _png_size(INTEGRATION_DIR / "brand" / image) == (size, size)


class TestHacsManifest:
    def test_hacs_json_points_at_the_repository_root_layout(self):
        hacs = json.loads(Path("hacs.json").read_text(encoding="utf-8"))
        assert hacs["name"] == MANIFEST["name"]
        # content_in_root=False means the integration lives in custom_components/
        assert hacs["content_in_root"] is False
        assert (INTEGRATION_DIR / "manifest.json").is_file()


def _requirement_floor(requirements: list[str], package: str) -> tuple[int, ...]:
    """Return the ``>=`` floor of ``package`` from a PEP 508 requirement list."""
    for requirement in requirements:
        name, _, version = requirement.partition(">=")
        if name.strip() == package:
            assert version, f"{package} is listed without a >= floor"
            return tuple(int(part) for part in version.split("."))
    raise AssertionError(f"{package} is not listed in {requirements}")


class TestToolingFloors:
    """The declared tool versions must be able to run this repository's gate.

    They could not: `ruff>=0.4` cannot even parse `target-version = "py314"` in
    pyproject.toml (it exits 2 with a TOML parse error) and predates PEP 758, and
    `mypy>=1.9` reports 5 errors on the very sources the pinned mypy accepts. The
    pre-commit rev was older still, so the hooks failed on every commit.
    """

    @staticmethod
    def _pyproject() -> dict:
        import tomllib

        return tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    def test_ruff_floor_can_parse_the_configured_target_version(self):
        floor = _requirement_floor(self._pyproject()["project"]["optional-dependencies"]["dev"], "ruff")
        # `target-version = "py314"` requires ruff >= 0.12; the flooring in the
        # dev extra is deliberately higher because UP038 changed behaviour in
        # between and flagged this codebase on 0.12.x.
        assert floor >= (0, 16)

    def test_mypy_floor_can_type_check_python_314(self):
        floor = _requirement_floor(self._pyproject()["project"]["optional-dependencies"]["dev"], "mypy")
        assert floor >= (2, 3)

    def test_pre_commit_ruff_rev_is_not_older_than_the_floor(self):
        """A pre-commit rev below the floor re-breaks the hooks."""
        import re

        floor = _requirement_floor(self._pyproject()["project"]["optional-dependencies"]["dev"], "ruff")
        config = Path(".pre-commit-config.yaml").read_text(encoding="utf-8")
        section = config.split("ruff-pre-commit", 1)[1]
        match = re.search(r"rev:\s*v?(\d+)\.(\d+)\.(\d+)", section)

        assert match is not None, "ruff-pre-commit has no pinned rev"
        assert tuple(int(part) for part in match.groups()) >= floor

    def test_ci_installs_the_same_spec_as_the_docs(self):
        """The floors live in pyproject.toml only, not repeated in the workflow."""
        workflow = (Path(".github") / "workflows" / "ci.yml").read_text(encoding="utf-8")
        install_lines = [
            line.strip()
            for line in workflow.splitlines()
            if line.strip().startswith(("pip install", "python -m pip install"))
        ]

        assert install_lines, "ci.yml no longer installs anything"
        assert any(".[test,dev]" in line for line in install_lines)
        # No tool floors re-declared here (comments are not install lines).
        assert not any("ruff>=" in line or "mypy>=" in line for line in install_lines)
