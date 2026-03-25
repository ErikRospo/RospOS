from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict


@dataclass
class TranslationUnitContext:
    tu: Dict = field(
        default_factory=lambda: {"globals": [], "functions": [], "types": []}
    )
    str_pool: Dict[str, str] = field(default_factory=dict)
    str_count: int = 0
    source_file: str = ""

    @property
    def source_dir(self) -> Path:
        if self.source_file:
            return Path(self.source_file).resolve().parent
        return Path.cwd()

    def get_or_create_string_label(self, value: str) -> str:
        for label, pooled_value in self.str_pool.items():
            if pooled_value == value:
                return label
        label = f"str_{self.str_count}"
        self.str_count += 1
        self.str_pool[label] = value
        self.tu["globals"].append({"kind": "string", "name": label, "value": value})
        return label
