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
        import tomllib

        from custom_components.smartsolar_ha.const import VERSION

        assert MANIFEST["version"] == VERSION

        pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
        assert pyproject["project"]["version"] == VERSION

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
        import yaml

        floor = _requirement_floor(self._pyproject()["project"]["optional-dependencies"]["dev"], "ruff")
        config = yaml.safe_load(Path(".pre-commit-config.yaml").read_text(encoding="utf-8"))
        ruff_repos = [repo for repo in config["repos"] if "ruff-pre-commit" in repo["repo"]]

        assert len(ruff_repos) == 1, "ruff-pre-commit is not declared exactly once"
        rev = ruff_repos[0]["rev"].removeprefix("v")
        assert tuple(int(part) for part in rev.split(".")) >= floor

    def test_ci_installs_the_same_spec_as_the_docs(self):
        """The floors live in pyproject.toml only, not repeated in the workflow."""
        import yaml

        workflow = yaml.safe_load((Path(".github") / "workflows" / "ci.yml").read_text(encoding="utf-8"))
        install_scripts = [
            step["run"]
            for step in workflow["jobs"]["lint"]["steps"]
            if isinstance(step.get("run"), str) and "pip install" in step["run"]
        ]

        assert install_scripts, "ci.yml lint job no longer installs anything"
        assert any(".[test,dev]" in script for script in install_scripts)
        # No tool floors re-declared here (comments are not part of the run script).
        assert not any("ruff>=" in script or "mypy>=" in script for script in install_scripts)


DEPLOY_SCRIPTS = ("deploy_to_ha.py", "upload_to_ha.py", "verify_live.py")


class TestScriptDependencies:
    """Every third-party module the helper scripts import must be installable.

    The scripts are documented as `python deploy_to_ha.py`, but `paramiko` was
    listed in no dependency set, so that command died with
    ``ModuleNotFoundError: No module named 'paramiko'`` on a fresh
    `pip install -e ".[test,dev]"`. This compares the *actual* imports of those
    scripts against the distributions pyproject declares, so the next such gap is
    caught without hard-coding a package name.
    """

    @staticmethod
    def _declared_distributions() -> set[str]:
        import tomllib

        project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
        requirements = list(project["dependencies"])
        for extra in project["optional-dependencies"].values():
            requirements.extend(extra)

        names = set()
        for requirement in requirements:
            # "aiohttp>=3.8.0" / "homeassistant==2026.9.2" / "pytest-cov>=5.0"
            for separator in ("<", ">", "=", "!", "~", "[", ";", " "):
                requirement = requirement.split(separator, 1)[0]
            names.add(requirement.strip().lower().replace("_", "-"))
        return names

    @staticmethod
    def _imported_top_level_modules(script: str) -> set[str]:
        import ast

        tree = ast.parse(Path(script).read_text(encoding="utf-8"))
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules.add(node.module.split(".")[0])
        return modules

    @pytest.mark.parametrize("script", DEPLOY_SCRIPTS)
    def test_script_imports_are_declared(self, script):
        import sys

        declared = self._declared_distributions()
        third_party = {
            module
            for module in self._imported_top_level_modules(script)
            if module not in sys.stdlib_module_names and module != "custom_components"
        }

        undeclared = {module for module in third_party if module.lower().replace("_", "-") not in declared}
        assert not undeclared, (
            f"{script} imports {sorted(undeclared)}, which no dependency or extra in pyproject.toml declares"
        )

    def test_deploy_extra_declares_paramiko(self):
        """The SSH scripts need paramiko, so an installable extra must carry it."""
        declared = self._declared_distributions()
        assert "paramiko" in declared
