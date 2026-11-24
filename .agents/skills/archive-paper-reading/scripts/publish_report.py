#!/usr/bin/env python3
"""Commit and push one generated paper report without mixing unrelated changes."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


WRITE_PERMISSIONS = {"WRITE", "MAINTAIN", "ADMIN"}


class PublishError(RuntimeError):
    pass


def run(command: list[str], cwd: Path, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise PublishError(f"{' '.join(command)} failed: {detail}")
    return result


def emit(status: str, **fields: object) -> None:
    print(json.dumps({"status": status, **fields}, ensure_ascii=False))


def github_slug(remote_url: str) -> str | None:
    prefixes = (
        "https://github.com/",
        "http://github.com/",
        "ssh://git@github.com/",
        "git@github.com:",
    )
    remainder = next((remote_url[len(prefix) :] for prefix in prefixes if remote_url.startswith(prefix)), None)
    if remainder is None:
        return None
    remainder = remainder.rstrip("/")
    if remainder.endswith(".git"):
        remainder = remainder[:-4]
    parts = remainder.split("/")
    return remainder if len(parts) == 2 and all(parts) else None


def relative_to_repo(path: Path, repo_root: Path) -> Path:
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(repo_root)
    except ValueError as exc:
        raise PublishError(f"publication path is outside the Git repository: {resolved}") from exc


def staged_paths(repo_root: Path) -> list[str]:
    output = run(
        ["git", "diff", "--cached", "--name-only", "-z"],
        repo_root,
    ).stdout
    return [item for item in output.split("\0") if item]


def path_allowed(path: str, exact: set[str], directories: tuple[str, ...]) -> bool:
    return path in exact or any(path.startswith(f"{directory}/") for directory in directories)


def publish(args: argparse.Namespace) -> int:
    workspace = args.workspace_root.expanduser().resolve()
    probe = run(["git", "-C", str(workspace), "rev-parse", "--show-toplevel"], workspace, check=False)
    if probe.returncode != 0:
        emit("skipped", reason="workspace is not inside a Git repository")
        return 0
    repo_root = Path(probe.stdout.strip()).resolve()

    remote = run(["git", "remote", "get-url", "upstream"], repo_root, check=False)
    if remote.returncode != 0:
        emit("skipped", reason="Git remote 'upstream' is not configured")
        return 0
    remote_url = remote.stdout.strip()
    repo_slug = github_slug(remote_url)
    if repo_slug is None:
        emit("skipped", reason="Git remote 'upstream' is not a github.com repository", remote=remote_url)
        return 0
    push_remote = run(["git", "remote", "get-url", "--push", "upstream"], repo_root, check=False)
    push_url = push_remote.stdout.strip() if push_remote.returncode == 0 else ""
    if github_slug(push_url) != repo_slug:
        emit(
            "skipped",
            reason="Git remote 'upstream' does not push to the same github.com repository",
            remote=remote_url,
            push_remote=push_url or None,
        )
        return 0

    branch_result = run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], repo_root, check=False)
    if branch_result.returncode != 0:
        emit("skipped", reason="cannot publish from a detached HEAD", repository=repo_slug)
        return 0
    branch = branch_result.stdout.strip()

    if shutil.which("gh") is None:
        emit("skipped", reason="GitHub CLI is unavailable; write permission cannot be verified", repository=repo_slug)
        return 0
    permission_result = run(
        ["gh", "repo", "view", repo_slug, "--json", "viewerPermission", "--jq", ".viewerPermission"],
        repo_root,
        check=False,
    )
    if permission_result.returncode != 0:
        emit("skipped", reason="GitHub authentication or permission lookup failed", repository=repo_slug)
        return 0
    permission = permission_result.stdout.strip().upper()
    if permission not in WRITE_PERMISSIONS:
        emit(
            "skipped",
            reason="authenticated GitHub account lacks write permission",
            repository=repo_slug,
            permission=permission or "UNKNOWN",
        )
        return 0

    report = args.report.expanduser().resolve()
    if not report.is_file():
        raise PublishError(f"report does not exist: {report}")
    index = report.parent / "index.html"
    if not index.is_file():
        raise PublishError(f"report index does not exist: {index}")
    assets = report.parent / "assets" / report.stem

    report_rel = relative_to_repo(report, repo_root)
    index_rel = relative_to_repo(index, repo_root)
    asset_rel = relative_to_repo(assets, repo_root) if assets.exists() else None
    pathspecs = [report_rel.as_posix(), index_rel.as_posix()]
    if asset_rel is not None:
        pathspecs.append(asset_rel.as_posix())

    existing_staged = staged_paths(repo_root)
    if existing_staged:
        emit(
            "skipped",
            reason="pre-existing staged changes would make automatic publication unsafe",
            staged=existing_staged[:20],
        )
        return 0

    changes = run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", *pathspecs],
        repo_root,
    ).stdout
    if not changes:
        emit("unchanged", repository=repo_slug, branch=branch, report=report_rel.as_posix())
        return 0

    if args.dry_run:
        emit(
            "dry_run",
            repository=repo_slug,
            permission=permission,
            branch=branch,
            remote=remote_url,
            paths=pathspecs,
        )
        return 0

    run(["git", "add", "--all", "--", *pathspecs], repo_root)
    staged = staged_paths(repo_root)
    exact = {report_rel.as_posix(), index_rel.as_posix()}
    directories = (asset_rel.as_posix(),) if asset_rel is not None else ()
    unexpected = [path for path in staged if not path_allowed(path, exact, directories)]
    if unexpected:
        run(["git", "restore", "--staged", "--", *pathspecs], repo_root, check=False)
        raise PublishError(f"refusing to mix unrelated staged paths: {', '.join(unexpected)}")
    if not staged:
        emit("unchanged", repository=repo_slug, branch=branch, report=report_rel.as_posix())
        return 0

    message = args.message or f"Add {report.stem} paper reading report"
    commit = run(
        ["git", "commit", "--only", "-m", message, "--", *pathspecs],
        repo_root,
        check=False,
    )
    if commit.returncode != 0:
        run(["git", "restore", "--staged", "--", *pathspecs], repo_root, check=False)
        raise PublishError(commit.stderr.strip() or commit.stdout.strip() or "git commit failed")
    local_sha = run(["git", "rev-parse", "HEAD"], repo_root).stdout.strip()

    push = run(
        ["git", "push", "upstream", f"HEAD:refs/heads/{branch}"],
        repo_root,
        check=False,
    )
    if push.returncode != 0:
        emit(
            "local_commit_only",
            reason=push.stderr.strip() or push.stdout.strip() or "git push failed",
            repository=repo_slug,
            branch=branch,
            commit=local_sha,
        )
        return 1

    remote_head = run(
        ["git", "ls-remote", "upstream", f"refs/heads/{branch}"],
        repo_root,
        check=False,
    )
    remote_sha = remote_head.stdout.split()[0] if remote_head.returncode == 0 and remote_head.stdout.strip() else ""
    if remote_sha != local_sha:
        emit(
            "verification_failed",
            reason="remote branch does not resolve to the pushed commit",
            repository=repo_slug,
            branch=branch,
            commit=local_sha,
            remote_commit=remote_sha or None,
        )
        return 1

    emit(
        "published",
        repository=repo_slug,
        permission=permission,
        branch=branch,
        commit=local_sha,
        commit_url=f"https://github.com/{repo_slug}/commit/{local_sha}",
        paths=staged,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--message")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        return publish(args)
    except PublishError as exc:
        emit("error", reason=str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
