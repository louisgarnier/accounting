#!/usr/bin/env python3
"""Git operations wrapper — use this for all git commands per CLAUDE.md."""
import subprocess
import sys
import argparse


def run(cmd: list[str]) -> int:
    """Run a git command, streaming output directly to terminal."""
    result = subprocess.run(cmd, check=False)
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Git operations wrapper",
        epilog="Example: python3 scripts/git_ops.py commit -m '[EPIC-1] feat: add feature'",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("status", help="Show working tree status")

    add_parser = subparsers.add_parser("add", help="Stage files")
    add_parser.add_argument("files", nargs="+", help="Files to stage")

    commit_parser = subparsers.add_parser("commit", help="Commit staged changes")
    commit_parser.add_argument("-m", "--message", required=True, help="Commit message")

    subparsers.add_parser("push", help="Push to remote")

    log_parser = subparsers.add_parser("log", help="Show commit log")
    log_parser.add_argument("--oneline", action="store_true", help="One line per commit")

    diff_parser = subparsers.add_parser("diff", help="Show changes")
    diff_parser.add_argument("args", nargs="*", help="Optional git diff arguments")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        print("\nError: a command is required.", file=sys.stderr)
        return 1

    if args.command == "status":
        return run(["git", "status"])
    elif args.command == "add":
        return run(["git", "add"] + args.files)
    elif args.command == "commit":
        return run(["git", "commit", "-m", args.message])
    elif args.command == "push":
        return run(["git", "push"])
    elif args.command == "log":
        cmd = ["git", "log"]
        if args.oneline:
            cmd.append("--oneline")
        return run(cmd)
    elif args.command == "diff":
        return run(["git", "diff"] + args.args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
