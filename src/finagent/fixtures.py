"""Explicitly fictional fixtures, with availability dates for as-of research."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path


def initialize(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    database = directory / "fundamentals.sqlite"
    if not database.exists():
        with closing(sqlite3.connect(database)) as conn:
            conn.execute("""CREATE TABLE fundamentals (
                symbol TEXT, period INTEGER, available_on TEXT,
                revenue REAL, operating_income REAL, debt REAL, equity REAL,
                operating_cash_flow REAL, capex REAL,
                PRIMARY KEY(symbol, period))""")
            conn.executemany(
                "INSERT INTO fundamentals VALUES (?,?,?,?,?,?,?,?,?)",
                [
                    ("ALFA", 2023, "2024-02-01", 100, 15, 40, 80, 20, 5),
                    ("ALFA", 2024, "2025-02-01", 125, 25, 45, 90, 30, 8),
                    ("BETA", 2023, "2024-02-15", 200, 20, 90, 100, 25, 10),
                    ("BETA", 2024, "2025-02-15", 180, 9, 120, 80, 18, 12),
                    ("ZERO", 2023, "2024-03-01", 0, -5, 10, 0, -2, 3),
                    ("ZERO", 2024, "2025-03-01", 20, -2, 15, 0, 1, 4),
                ],
            )
            conn.commit()
    docs = directory / "documents.json"
    if not docs.exists():
        docs.write_text(
            json.dumps(
                [
                    {
                        "id": "alfa-risk",
                        "symbol": "ALFA",
                        "available_on": "2025-02-01",
                        "source": "fictional:ALFA/2024/risk",
                        "text": "ALFA risk factors: customer concentration and supplier disruptions can reduce profitability. Management describes recurring subscription revenue and international expansion.",
                    },
                    {
                        "id": "alfa-old",
                        "symbol": "ALFA",
                        "available_on": "2024-02-01",
                        "source": "fictional:ALFA/2023/risk",
                        "text": "ALFA risk factors: foreign exchange exposure and dependency on a single supplier.",
                    },
                    {
                        "id": "beta-risk",
                        "symbol": "BETA",
                        "available_on": "2025-02-15",
                        "source": "fictional:BETA/2024/risk",
                        "text": "BETA risk factors: refinancing debt, weakening demand and interest expense. Management reports a restructuring program.",
                    },
                    {
                        "id": "zero-risk",
                        "symbol": "ZERO",
                        "available_on": "2025-03-01",
                        "source": "fictional:ZERO/2024/risk",
                        "text": "ZERO risk factors: operating losses and liquidity pressure. Equity is depleted and the revenue base is small.",
                    },
                    {
                        "id": "future-risk",
                        "symbol": "ALFA",
                        "available_on": "2030-01-01",
                        "source": "fictional:ALFA/future",
                        "text": "ALFA risk factors: future report must not appear in earlier research.",
                    },
                ],
                indent=2,
            ),
            encoding="utf-8",
        )
    market = directory / "market.json"
    if not market.exists():
        market.write_text(
            json.dumps(
                {
                    "ALFA": {"date": "2025-03-03", "close": 42.0},
                    "BETA": {"date": "2025-03-03", "close": 18.5},
                    "ZERO": {"date": "2025-03-03", "close": 2.0},
                },
                indent=2,
            ),
            encoding="utf-8",
        )
