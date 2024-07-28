from enum import IntFlag


class Level(IntFlag):
    LOW = 0
    MEDIUM = 1
    HIGH = 2


LOW = Level.LOW
MEDIUM = Level.MEDIUM
HIGH = Level.HIGH

__all__ = [
    "Level",
]
