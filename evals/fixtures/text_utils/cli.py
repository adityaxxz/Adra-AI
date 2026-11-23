"""Command line entry point: print the slug of the text given as the first argument."""
import sys

from strings import slugify


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: cli.py TEXT")
        return 1
    print(slugify(argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
