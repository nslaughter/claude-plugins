#!/usr/bin/env python3
"""Post one review's findings to a pull request, each where its problem is.

Reviewers never post. They return findings, and this script posts each one as close to its code
as GitHub allows:

1. **On a line the PR's diff shows:** an inline comment on that line, in one comment-only review
   (event COMMENT), which also carries the reviewer's summary.
2. **On another line of a file the PR changes:** GitHub takes line comments only on diff lines,
   so the finding becomes a comment on the file (`subject_type: file`), headed by the line it
   names, quoted from the checkout when `--source` is given. It still gets a thread of its own.
3. **In a file the PR doesn't change:** in the review's body. Only these have no thread.

It never approves or requests changes. It writes each finding's comment ID, or null for one in
the body, with how it was anchored, so the fix agent can reply under each thread.

Usage:
  post_review.py --pr 13 --commit <head sha> --review 1 --findings review-1.json \
      --out comments-1.json [--source <checkout at the head>] [--repo owner/name] \
      [--dry-run | --map-review REVIEW_ID]

Needs only Python 3 and an authenticated `gh`. With --dry-run it fetches the PR's files, prints
what it would post, and posts nothing.
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def gh(*args: str) -> str:
    result = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])} failed: {result.stderr.strip()}")
    return result.stdout


def gh_send(endpoint: str, payload: dict, method: str = "POST") -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as file:
        json.dump(payload, file)
    try:
        return json.loads(gh("api", "-X", method, endpoint, "--input", file.name))
    finally:
        Path(file.name).unlink()


def commentable_lines(patch: str) -> set[int]:
    """The new-file line numbers a review comment can anchor to: added and context lines."""
    lines: set[int] = set()
    current = 0
    for text in patch.splitlines():
        match = HUNK.match(text)
        if match:
            current = int(match.group(1))
            continue
        if text.startswith("-") or text.startswith("\\"):
            continue  # Removed lines exist only on the left; "\ No newline" is a marker.
        lines.add(current)
        current += 1
    return lines


def diff_lines(repo: str, pr: int) -> dict[str, set[int]]:
    """Each file the PR changes, with the lines its diff shows. A file with no patch, such as a
    large or binary one, maps to no lines, and so takes only a file comment."""
    pages = gh("api", "--paginate", "--slurp", f"repos/{repo}/pulls/{pr}/files")
    files = [entry for page in json.loads(pages) for entry in page]
    return {f["filename"]: commentable_lines(f.get("patch") or "") for f in files}


def heading(finding: dict) -> str:
    return f"**[{finding['severity']}] {finding['category']}: {finding['title']}**"


def quoted_line(source: Path | None, path: str, line: int) -> str | None:
    """The text of `path`'s line `line` in the checkout `source`, if there is one to read."""
    if source is None:
        return None
    try:
        text = (source / path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    return text[line - 1] if 0 < line <= len(text) else None


def file_comment_body(finding: dict, source: Path | None) -> str:
    where = f"Line {finding['line']}, which this PR doesn't change:"
    text = quoted_line(source, finding["path"], finding["line"])
    if text is not None:
        fence = "````" if "```" in text else "```"
        where += f"\n\n{fence}\n{text}\n{fence}"
    return f"{heading(finding)}\n\n{where}\n\n{finding['body']}"


def build(
    findings: dict,
    lines: dict[str, set[int]],
    review_number: int,
    commit: str,
    source: Path | None,
    *,
    inline_allowed: bool = True,
) -> dict:
    inline: list[tuple[int, dict]] = []
    on_file: list[tuple[int, dict]] = []
    outside: list[int] = []
    for index, finding in enumerate(findings["findings"]):
        path, line = finding["path"], finding["line"]
        if inline_allowed and line in lines.get(path, set()):
            body = f"{heading(finding)}\n\n{finding['body']}"
            inline.append((index, {"path": path, "line": line, "side": "RIGHT", "body": body}))
        elif path in lines:
            on_file.append((index, {
                "commit_id": commit,
                "path": path,
                "subject_type": "file",
                "body": file_comment_body(finding, source),
            }))
        else:
            outside.append(index)
    review = {
        "commit_id": commit,
        "event": "COMMENT",
        "body": review_body(findings, review_number, [i for i, _ in on_file], outside),
        "comments": [comment for _, comment in inline],
    }
    return {"review": review, "inline": [i for i, _ in inline], "file": on_file, "outside": outside}


def review_body(findings: dict, review_number: int, on_file: list[int], outside: list[int]) -> str:
    items = findings["findings"]
    parts = [f"Automated review {review_number} of at most 3.", "", findings["summary"]]
    if not items:
        parts += ["", "No findings."]
    if on_file:
        parts += ["", "### Findings on lines this PR doesn't change", ""]
        parts += [
            f"{i + 1}. {heading(items[i])} (`{items[i]['path']}:{items[i]['line']}`): a comment"
            " on its file."
            for i in on_file
        ]
    if outside:
        parts += ["", "### Findings in files this PR doesn't change", ""]
        for i in outside:
            parts += [f"{i + 1}. {heading(items[i])} (`{items[i]['path']}:{items[i]['line']}`)", ""]
            parts += [items[i]["body"], ""]
    return "\n".join(parts).rstrip() + "\n"


def pr_comments(repo: str, pr: int) -> list[dict]:
    pages = gh("api", "--paginate", "--slurp", f"repos/{repo}/pulls/{pr}/comments")
    return [c for page in json.loads(pages) for c in page]


def map_inline(repo: str, pr: int, review_id: int, plan: dict) -> dict[int, int]:
    """Each inline finding's comment ID. The per-review comments endpoint omits `line`, so this
    reads the PR's comments, which carry it, keeps this review's, and matches by path, line, and
    body."""
    comments = [c for c in pr_comments(repo, pr) if c.get("pull_request_review_id") == review_id]
    ids: dict[int, int] = {}
    for index, sent in zip(plan["inline"], plan["review"]["comments"]):
        for comment in comments:
            line = comment.get("line") or comment.get("original_line")
            if (comment["path"], line, comment["body"]) == (sent["path"], sent["line"], sent["body"]):
                ids[index] = comment["id"]
                comments.remove(comment)
                break
    return ids


def map_file_comments(repo: str, pr: int, plan: dict) -> dict[int, int]:
    """Each file comment's ID, found among the PR's file comments by path and body."""
    comments = [c for c in pr_comments(repo, pr) if c.get("subject_type") == "file"]
    ids: dict[int, int] = {}
    for index, sent in plan["file"]:
        for comment in comments:
            if (comment["path"], comment["body"]) == (sent["path"], sent["body"]):
                ids[index] = comment["id"]
                comments.remove(comment)
                break
    return ids


def mapping(findings: dict, inline: dict[int, int], on_file: dict[int, int]) -> list[dict]:
    result = []
    for i in range(len(findings["findings"])):
        if i in inline:
            result.append({"finding": i, "comment_id": inline[i], "anchor": "line"})
        elif i in on_file:
            result.append({"finding": i, "comment_id": on_file[i], "anchor": "file"})
        else:
            result.append({"finding": i, "comment_id": None, "anchor": "body"})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--commit", required=True, help="the head SHA that was reviewed")
    parser.add_argument("--review", type=int, required=True, help="the review's number, 1 to 3")
    parser.add_argument("--findings", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--source", type=Path, help="a checkout at --commit, to quote the line of a file comment"
    )
    parser.add_argument("--repo", help="owner/name; defaults to the current repository")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--map-review",
        type=int,
        metavar="REVIEW_ID",
        help="don't post: write --out for this already-posted review of these findings",
    )
    args = parser.parse_args()

    repo = args.repo or gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner").strip()
    findings = json.loads(args.findings.read_text())
    lines = diff_lines(repo, args.pr)
    plan = build(findings, lines, args.review, args.commit, args.source)

    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return 0
    if args.map_review is not None:
        result = mapping(
            findings,
            map_inline(repo, args.pr, args.map_review, plan),
            map_file_comments(repo, args.pr, plan),
        )
        args.out.write_text(
            json.dumps({"review_id": args.map_review, "comments": result}, indent=2) + "\n"
        )
        print(json.dumps({
            "review_id": args.map_review,
            "mapped": sum(m["comment_id"] is not None for m in result),
        }))
        return 0

    reviews = f"repos/{repo}/pulls/{args.pr}/reviews"
    try:
        created = gh_send(reviews, plan["review"])
    except RuntimeError as error:
        # A line GitHub won't take (422) fails the whole review: put those findings on their
        # files instead.
        if "422" not in str(error) or not plan["inline"]:
            raise
        print(f"Inline comments refused ({error}); posting them on their files.", file=sys.stderr)
        plan = build(findings, lines, args.review, args.commit, args.source, inline_allowed=False)
        created = gh_send(reviews, plan["review"])
    inline = map_inline(repo, args.pr, created["id"], plan)

    # File comments go one at a time: the review endpoint takes only line comments.
    on_file: dict[int, int] = {}
    refused: list[int] = []
    for index, payload in plan["file"]:
        try:
            on_file[index] = gh_send(f"repos/{repo}/pulls/{args.pr}/comments", payload)["id"]
        except RuntimeError as error:
            print(f"File comment for finding {index + 1} refused ({error}).", file=sys.stderr)
            refused.append(index)
    if refused:
        # Move the refused ones into the review's body, so no finding is lost.
        kept = [i for i, _ in plan["file"] if i not in refused]
        body = review_body(findings, args.review, kept, sorted([*plan["outside"], *refused]))
        gh_send(f"{reviews}/{created['id']}", {"body": body}, method="PUT")

    result = mapping(findings, inline, on_file)
    args.out.write_text(
        json.dumps(
            {"review_id": created["id"], "url": created.get("html_url"), "comments": result},
            indent=2,
        )
        + "\n"
    )
    print(json.dumps({
        "review_id": created["id"],
        "url": created.get("html_url"),
        "inline": len(inline),
        "on_file": len(on_file),
        "in_body": len(findings["findings"]) - len(inline) - len(on_file),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
