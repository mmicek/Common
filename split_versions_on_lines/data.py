from dataclasses import dataclass, field


@dataclass
class Version:
    version_id: str | None = None
    quantity: int = 0


@dataclass
class LineConfiguration:
    pk: int
    pockets: int
    min_quantity_per_line: int
    max_quantity_all_lines: int


@dataclass
class Line:
    line_configuration: LineConfiguration | None = None
    versions: set[Version] = field(default_factory=lambda: set())


@dataclass
class CoMailFacility:
    line_configs: list[LineConfiguration]
    lines: list[Line] = field(default_factory=lambda: [])
