"""Sandbox entry point for CM integration tests."""

from lib.helpers import greet, add_numbers


def main() -> None:
    print(greet("world"))
    print(add_numbers(2, 3))


if __name__ == "__main__":
    main()
