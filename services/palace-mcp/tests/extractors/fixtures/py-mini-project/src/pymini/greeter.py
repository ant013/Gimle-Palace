"""Greeter module — mirrors ts-mini-project/src/greeter.ts structure."""

from dataclasses import dataclass


@dataclass
class Greeting:
    message: str
    recipient: str


class Greeter:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix

    def greet(self, name: str) -> Greeting:
        return Greeting(message=f"{self.prefix} {name}", recipient=name)

    def greet_all(self, names: list[str]) -> list[Greeting]:
        return [self.greet(n) for n in names]


def format_greeting(g: Greeting) -> str:
    return f"[{g.recipient}] {g.message}"
