import functools


class Logger:
    def __init__(self, name: str) -> None:
        self.name = name

    @functools.lru_cache(maxsize=128)
    def get_message(self, text: str) -> str:
        return f"[{self.name}] {text}"

    def log(self, message: str) -> None:
        print(self.get_message(message))
