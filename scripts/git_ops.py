#!/usr/bin/env python3
"""Git operations wrapper — use this for all git commands per CLAUDE.md."""
import subprocess
import sys
import argparse


def run(cmd: list[str]) -> int:
    result = subprocess.run(cmd, check=False)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="Git operations wrapper")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("status")

    add_parser = subparsers.add_parser("add")
    add_parser.add_argument("files", nargs="+")

    commit_parser = subparsers.add_parser("commit")
    commit_parser.add_argument("-m", "--message", required=True)

    subparsers.add_parser("push")

    log_parser = subparsers.add_parser("log")
    log_parser.add_argument("--oneline", action="store_true")

    diff_parser = subparsers.add_parser("diff")
    diff_parser.add_argument("args", nargs="*")

    args = parser.parse_args()

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
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
