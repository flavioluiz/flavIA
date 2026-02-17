"""Tests for agent permissions parsing and inheritance."""

import pytest

from flavia.agent.profile import AgentPermissions, AgentProfile


def test_permissions_write_implies_read(tmp_path):
    base_dir = tmp_path.resolve()
    permissions = AgentPermissions.from_config(
        {
            "read": ["./docs"],
            "write": ["./output"],
        },
        base_dir=base_dir,
    )

    assert permissions.can_read(base_dir / "docs" / "a.txt")
    assert permissions.can_read(base_dir / "output" / "b.txt")
    assert permissions.can_write(base_dir / "output" / "b.txt")
    assert not permissions.can_write(base_dir / "docs" / "a.txt")


def test_permissions_from_config_marks_as_explicit(tmp_path):
    permissions = AgentPermissions.from_config({}, base_dir=tmp_path.resolve())
    assert permissions.explicit is True
    assert permissions.read_paths == []
    assert permissions.write_paths == []


def test_subagent_inherits_permissions_as_copy(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    profile = AgentProfile.from_config(
        {
            "context": "main",
            "permissions": {
                "read": ["./docs"],
                "write": ["./output"],
            },
            "subagents": {
                "child": {
                    "context": "child",
                    "tools": ["read_file"],
                }
            },
        }
    )

    child = profile.create_subagent_profile("child")
    assert child is not None
    assert child.permissions.read_paths == profile.permissions.read_paths
    assert child.permissions.write_paths == profile.permissions.write_paths
    assert child.permissions is not profile.permissions


def test_allow_converted_read_defaults_to_false(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    profile = AgentProfile.from_config({"context": "main"})
    assert profile.allow_converted_read is False
    assert profile.converted_access_mode == "hybrid"


def test_allow_converted_read_inheritance_and_override(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    profile = AgentProfile.from_config(
        {
            "context": "main",
            "allow_converted_read": True,
            "subagents": {
                "child": {
                    "context": "child",
                    "tools": ["read_file"],
                },
                "strict_child": {
                    "context": "strict",
                    "allow_converted_read": False,
                    "tools": ["read_file"],
                },
            },
        }
    )

    child = profile.create_subagent_profile("child")
    strict_child = profile.create_subagent_profile("strict_child")
    assert child is not None
    assert strict_child is not None
    assert child.allow_converted_read is True
    assert strict_child.allow_converted_read is False
    assert child.converted_access_mode == "open"
    assert strict_child.converted_access_mode == "strict"


def test_converted_access_mode_inheritance_and_override(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    profile = AgentProfile.from_config(
        {
            "context": "main",
            "converted_access_mode": "hybrid",
            "subagents": {
                "child": {
                    "context": "child",
                    "tools": ["read_file"],
                },
                "reader": {
                    "context": "reader",
                    "converted_access_mode": "open",
                    "tools": ["read_file"],
                },
            },
        }
    )

    child = profile.create_subagent_profile("child")
    reader = profile.create_subagent_profile("reader")
    assert child is not None
    assert reader is not None
    assert child.converted_access_mode == "hybrid"
    assert reader.converted_access_mode == "open"
    assert child.allow_converted_read is False
    assert reader.allow_converted_read is True


def test_converted_access_mode_rejects_invalid_value(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="converted_access_mode"):
        AgentProfile.from_config({"context": "main", "converted_access_mode": "invalid"})


def test_converted_access_mode_conflict_with_legacy_flag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="conflicts with converted_access_mode"):
        AgentProfile.from_config(
            {
                "context": "main",
                "converted_access_mode": "strict",
                "allow_converted_read": True,
            }
        )
