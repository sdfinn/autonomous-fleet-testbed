"""Tests for tools.ghcr_prune's pure version-selection logic (Piece 6)."""

from tools.ghcr_prune import select_versions_to_delete


def _version(id_, created_at, tags=None):
    return {
        "id": id_,
        "created_at": created_at,
        "metadata": {"container": {"tags": tags or []}},
    }


def test_keeps_the_newest_n_unprotected_versions():
    versions = [
        _version(1, "2026-07-01T00:00:00Z"),
        _version(2, "2026-07-02T00:00:00Z"),
        _version(3, "2026-07-03T00:00:00Z"),
    ]

    deleted = select_versions_to_delete(versions, keep_n=2, protected_tags={"latest"})

    assert [v["id"] for v in deleted] == [1]


def test_never_selects_a_version_carrying_a_protected_tag():
    versions = [
        _version(1, "2026-07-01T00:00:00Z", tags=["latest"]),
        _version(2, "2026-07-02T00:00:00Z", tags=["buildcache-v2"]),
        _version(3, "2026-07-03T00:00:00Z"),
        _version(4, "2026-07-04T00:00:00Z"),
    ]

    deleted = select_versions_to_delete(
        versions, keep_n=1, protected_tags={"latest", "buildcache-v2"}
    )

    assert [v["id"] for v in deleted] == [3]


def test_keeps_everything_when_fewer_unprotected_versions_than_keep_n():
    versions = [
        _version(1, "2026-07-01T00:00:00Z"),
        _version(2, "2026-07-02T00:00:00Z"),
    ]

    deleted = select_versions_to_delete(versions, keep_n=15, protected_tags={"latest"})

    assert deleted == []


def test_empty_version_list_selects_nothing():
    assert select_versions_to_delete([], keep_n=15, protected_tags={"latest"}) == []
