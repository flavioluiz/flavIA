"""Tests for agent permissions parsing and inheritance."""

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
