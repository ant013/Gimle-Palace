from dataclasses import dataclass


@dataclass
class Config:
    name: str
    debug: bool = False
    max_retries: int = 3
