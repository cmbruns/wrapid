from enum import IntFlag


class Level(IntFlag):
    LOW = 0
    MEDIUM = 1
    HIGH = 2


__all__ = [
    "Level",
]
