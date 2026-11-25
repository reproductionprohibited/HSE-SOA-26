from pathlib import Path

# SQL-файлы выполняются по порядку имён: 05_retention_metrics читает результат 04_retention_cohort
QUERIES: list[tuple[str, str]] = [
    (p.stem, p.read_text()) for p in sorted(Path(__file__).parent.glob("*.sql"))
]
