"""Tests for the plugin architecture."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from rpa_architect.plugins import (
    HookPoint,
    discover_plugins,
    get_registered_namespaces,
    load_plugin,
    register_generator,
    register_lint_rule,
    register_namespace,
    register_scaffold_hook,
    run_hooks,
)
from rpa_architect.plugins.hooks import clear_hooks, _HOOKS
from rpa_architect.plugins.loader import clear_plugins, get_loaded_plugins, _LOADED_PLUGINS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_hooks_and_plugins():
    """Reset hooks and plugins before and after each test."""
    clear_hooks()
    clear_plugins()
    yield
    clear_hooks()
    clear_plugins()


@pytest.fixture
def _reset_namespaces():
    """Reset the custom namespaces registry."""
    from rpa_architect.plugins.api import _CUSTOM_NAMESPACES
    original = dict(_CUSTOM_NAMESPACES)
    _CUSTOM_NAMESPACES.clear()
    yield
    _CUSTOM_NAMESPACES.clear()
    _CUSTOM_NAMESPACES.update(original)


# ===================================================================
# register_generator()
# ===================================================================

class TestRegisterGenerator:

    def test_registers_to_generators_registry(self):
        from rpa_architect.generators.registry import get_generator, _REGISTRY

        # Use a unique name that won't conflict
        unique_name = "__test_plugin_gen_xyz__"
        assert unique_name not in _REGISTRY

        def my_gen(**kwargs):
            return "<MyActivity />"

        try:
            register_generator(
                unique_name,
                my_gen,
                display_name="My Activity",
                category="test",
                description="A test generator",
            )
            info = get_generator(unique_name)
            assert info is not None
            assert info.name == unique_name
            assert info.fn is my_gen
            assert info.category == "test"
        finally:
            # Clean up the registry
            _REGISTRY.pop(unique_name, None)

    def test_duplicate_name_raises(self):
        from rpa_architect.generators.registry import _REGISTRY

        unique_name = "__test_plugin_dup__"
        _REGISTRY.pop(unique_name, None)

        def gen_fn(**kwargs):
            return "<X />"

        try:
            register_generator(unique_name, gen_fn, category="test")
            with pytest.raises(ValueError, match="already registered"):
                register_generator(unique_name, gen_fn, category="test")
        finally:
            _REGISTRY.pop(unique_name, None)


# ===================================================================
# register_lint_rule()
# ===================================================================

class TestRegisterLintRule:

    def test_adds_to_default_engine(self):
        from rpa_architect.xaml_lint.engine import get_default_engine

        engine = get_default_engine()
        initial_count = engine.rule_count

        def my_rule(root: ET.Element, ns: dict) -> list:
            return []

        register_lint_rule(my_rule, rule_module="test")
        assert engine.rule_count == initial_count + 1


# ===================================================================
# register_namespace()
# ===================================================================

class TestRegisterNamespace:

    def test_stores_custom_namespace(self, _reset_namespaces):
        register_namespace("myext", "http://example.com/myext")
        ns = get_registered_namespaces()
        assert "myext" in ns
        assert ns["myext"] == "http://example.com/myext"

    def test_multiple_namespaces(self, _reset_namespaces):
        register_namespace("ns1", "http://example.com/ns1")
        register_namespace("ns2", "http://example.com/ns2")
        ns = get_registered_namespaces()
        assert "ns1" in ns
        assert "ns2" in ns

    def test_get_registered_returns_copy(self, _reset_namespaces):
        register_namespace("test", "http://test.com")
        ns1 = get_registered_namespaces()
        ns1["injected"] = "should not appear"
        ns2 = get_registered_namespaces()
        assert "injected" not in ns2


# ===================================================================
# register_scaffold_hook()
# ===================================================================

class TestRegisterScaffoldHook:

    def test_registers_at_correct_hook_point(self):
        def my_hook(ctx):
            return ctx

        register_scaffold_hook(my_hook, hook_point="pre_scaffold")
        assert my_hook in _HOOKS[HookPoint.PRE_SCAFFOLD]

    def test_registers_post_scaffold_by_default(self):
        def another_hook(ctx):
            return ctx

        register_scaffold_hook(another_hook)
        assert another_hook in _HOOKS[HookPoint.POST_SCAFFOLD]

    def test_all_hook_points(self):
        for hp in HookPoint:
            def hook(ctx, _hp=hp):
                return ctx

            register_scaffold_hook(hook, hook_point=hp.value)
            assert hook in _HOOKS[hp]


# ===================================================================
# run_hooks()
# ===================================================================

class TestRunHooks:

    def test_hooks_receive_context(self):
        received = {}

        def capture_hook(ctx):
            received.update(ctx)

        register_scaffold_hook(capture_hook, hook_point="pre_scaffold")
        run_hooks(HookPoint.PRE_SCAFFOLD, {"key": "value"})
        assert received == {"key": "value"}

    def test_hooks_can_modify_context(self):
        def add_key_hook(ctx):
            ctx["added"] = True
            return ctx

        register_scaffold_hook(add_key_hook, hook_point="pre_scaffold")
        result = run_hooks(HookPoint.PRE_SCAFFOLD, {"original": True})
        assert result["original"] is True
        assert result["added"] is True

    def test_hooks_chain_context(self):
        def hook_a(ctx):
            ctx["a"] = True
            return ctx

        def hook_b(ctx):
            ctx["b"] = True
            # hook_b should see hook_a's modification
            assert ctx.get("a") is True
            return ctx

        register_scaffold_hook(hook_a, hook_point="pre_assemble")
        register_scaffold_hook(hook_b, hook_point="pre_assemble")
        result = run_hooks(HookPoint.PRE_ASSEMBLE, {})
        assert result["a"] is True
        assert result["b"] is True

    def test_hook_exception_does_not_stop_others(self):
        call_log = []

        def bad_hook(ctx):
            call_log.append("bad")
            raise RuntimeError("boom")

        def good_hook(ctx):
            call_log.append("good")
            return ctx

        register_scaffold_hook(bad_hook, hook_point="post_scaffold")
        register_scaffold_hook(good_hook, hook_point="post_scaffold")
        run_hooks(HookPoint.POST_SCAFFOLD, {})
        assert "bad" in call_log
        assert "good" in call_log

    def test_hook_returning_none_preserves_context(self):
        def noop_hook(ctx):
            # Returns None implicitly
            pass

        register_scaffold_hook(noop_hook, hook_point="pre_validate")
        result = run_hooks(HookPoint.PRE_VALIDATE, {"keep": "me"})
        assert result["keep"] == "me"


# ===================================================================
# discover_plugins()
# ===================================================================

class TestDiscoverPlugins:

    def test_finds_py_files_in_extensions_dir(self, tmp_path: Path):
        ext_dir = tmp_path / "extensions"
        ext_dir.mkdir()
        (ext_dir / "plugin_a.py").write_text("# plugin a", encoding="utf-8")
        (ext_dir / "plugin_b.py").write_text("# plugin b", encoding="utf-8")
        # Private files should be skipped
        (ext_dir / "_private.py").write_text("# private", encoding="utf-8")

        discovered = discover_plugins(ext_dir)
        names = [d for d in discovered]
        assert any("plugin_a" in n for n in names)
        assert any("plugin_b" in n for n in names)
        assert not any("_private" in n for n in names)

    def test_nonexistent_dir_returns_empty(self, tmp_path: Path):
        fake = tmp_path / "no_such_dir"
        discovered = discover_plugins(fake)
        assert discovered == []

    def test_finds_sub_packages(self, tmp_path: Path):
        ext_dir = tmp_path / "extensions"
        ext_dir.mkdir()
        sub_pkg = ext_dir / "my_plugin_pkg"
        sub_pkg.mkdir()
        (sub_pkg / "__init__.py").write_text("# package init", encoding="utf-8")

        discovered = discover_plugins(ext_dir)
        assert any("my_plugin_pkg" in d for d in discovered)

    def test_empty_dir_returns_empty(self, tmp_path: Path):
        ext_dir = tmp_path / "extensions"
        ext_dir.mkdir()
        discovered = discover_plugins(ext_dir)
        assert discovered == []


# ===================================================================
# load_plugin()
# ===================================================================

class TestLoadPlugin:

    def test_loads_module_by_path(self, tmp_path: Path):
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text(
            "LOADED = True\n",
            encoding="utf-8",
        )

        module = load_plugin("test_plugin_via_path", plugin_path=plugin_file)
        assert module.LOADED is True

    def test_caches_loaded_module(self, tmp_path: Path):
        plugin_file = tmp_path / "cached_plugin.py"
        plugin_file.write_text("VALUE = 42\n", encoding="utf-8")

        mod1 = load_plugin("cached_plugin_test", plugin_path=plugin_file)
        mod2 = load_plugin("cached_plugin_test", plugin_path=plugin_file)
        assert mod1 is mod2

    def test_load_nonexistent_raises(self):
        with pytest.raises(Exception):
            load_plugin("__nonexistent_plugin_xyz__")


# ===================================================================
# clear_hooks() and clear_plugins()
# ===================================================================

class TestClearFunctions:

    def test_clear_hooks_empties_all(self):
        def hook(ctx):
            return ctx

        for hp in HookPoint:
            register_scaffold_hook(hook, hook_point=hp.value)

        clear_hooks()
        for hp in HookPoint:
            assert len(_HOOKS[hp]) == 0

    def test_clear_plugins_empties_cache(self, tmp_path: Path):
        plugin_file = tmp_path / "disposable.py"
        plugin_file.write_text("X = 1\n", encoding="utf-8")
        load_plugin("disposable_test", plugin_path=plugin_file)
        assert "disposable_test" in get_loaded_plugins()

        clear_plugins()
        assert "disposable_test" not in get_loaded_plugins()
