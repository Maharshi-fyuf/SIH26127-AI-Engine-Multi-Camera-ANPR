from dataclasses import dataclass
from typing import Dict


@dataclass
class MigrationCheck:
    table_name: str
    sqlite_rows: int
    postgres_rows: int

    @property
    def passed(self) -> bool:
        return self.sqlite_rows == self.postgres_rows


def migration_report(checks: Dict[str, MigrationCheck]) -> str:
    lines = ["# SQLite to Postgres Migration Report", ""]
    for check in checks.values():
        status = "PASS" if check.passed else "FAIL"
        lines.append(f"- {status}: {check.table_name} sqlite={check.sqlite_rows} postgres={check.postgres_rows}")
    return "\n".join(lines) + "\n"
