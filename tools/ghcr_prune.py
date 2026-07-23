"""GHCR image-version retention (Session 17 Piece 6).

CI pushes a uniquely git-sha-tagged arm64 image per build (stage-3-arm64) and
never deletes an old one — the registry grows forever. This selects which
versions are safe to delete (newest N unprotected versions kept, everything
else eligible) and, with --delete, actually removes them via the GitHub API.

Third-party GHA actions for this exist, but their exact tag-protection
semantics aren't something we can verify without running one for real against
a registry we can't easily undo — so this is a small, fully unit-testable
tool instead, run in --delete=false (report-only) mode until a human reviews
a real report and decides to flip it on. See .github/workflows/ghcr-cleanup.yml.

Usage:
    python -m tools.ghcr_prune --owner sdfinn --package autonomous-fleet-testbed \
        --keep-n 15 --protect latest --protect buildcache-v2 [--delete]
"""

import argparse
import json
import subprocess
import sys


def select_versions_to_delete(versions, keep_n, protected_tags):
    """Return the subset of `versions` eligible for deletion.

    `versions` is a list of dicts shaped like the GitHub packages API
    (`id`, `created_at`, `metadata.container.tags`). Any version carrying a
    protected tag is never selected. Among the remaining (unprotected)
    versions, the `keep_n` most recently created are kept; anything older is
    returned, newest-of-the-deleted-set first.
    """
    def tags_of(version):
        return set(version.get("metadata", {}).get("container", {}).get("tags", []))

    unprotected = [v for v in versions if not (tags_of(v) & protected_tags)]
    unprotected.sort(key=lambda v: v["created_at"], reverse=True)
    return unprotected[keep_n:]


def _gh_api_list(owner, package, package_type):
    result = subprocess.run(
        ["gh", "api", "--paginate",
         f"/{package_type}s/{owner}/packages/container/{package}/versions"],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def _gh_api_delete(owner, package, package_type, version_id):
    subprocess.run(
        ["gh", "api", "-X", "DELETE",
         f"/{package_type}s/{owner}/packages/container/{package}/versions/{version_id}"],
        check=True,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--keep-n", type=int, default=15)
    parser.add_argument("--protect", action="append", default=[])
    parser.add_argument("--type", choices=["org", "user"], default="user")
    parser.add_argument(
        "--delete", action="store_true",
        help="Actually delete candidates. Without this flag, report only.",
    )
    args = parser.parse_args(argv)

    protected_tags = set(args.protect) or {"latest"}
    versions = _gh_api_list(args.owner, args.package, args.type)
    to_delete = select_versions_to_delete(versions, args.keep_n, protected_tags)

    print(f"Total versions: {len(versions)}, kept: {len(versions) - len(to_delete)}, "
          f"candidates for deletion: {len(to_delete)}")
    for v in to_delete:
        tags = sorted(v.get("metadata", {}).get("container", {}).get("tags", []))
        print(f"  id={v['id']} tags={tags} created_at={v['created_at']}")

    if not args.delete:
        print("Report only — nothing deleted. Pass --delete to actually prune.")
        return 0

    for v in to_delete:
        _gh_api_delete(args.owner, args.package, args.type, v["id"])
    print(f"Deleted {len(to_delete)} version(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
