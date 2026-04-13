"""
Prepare the demo sample dataset from the NYC Taxi parquet file.
Creates a 10,000-row CSV sample in examples/ for easy demo use.

Usage: python examples/generate_sample.py
Requires: duckdb, pandas
"""
import sys
from pathlib import Path

SOURCE = Path(__file__).parent.parent.parent / "nyc-taxi-pipeline" / "data" / "raw" / "yellow_tripdata_2023-01.parquet"
OUT_CSV = Path(__file__).parent / "nyc_taxi_sample.csv"
SAMPLE_ROWS = 10_000


def main() -> None:
    try:
        import duckdb
    except ImportError:
        print("Install duckdb: pip install duckdb")
        sys.exit(1)

    if not SOURCE.exists():
        print(f"Source not found: {SOURCE}")
        print("Place yellow_tripdata_2023-01.parquet in examples/ or adjust SOURCE path.")
        sys.exit(1)

    conn = duckdb.connect()
    conn.execute("INSTALL httpfs; LOAD httpfs;")

    conn.execute(f"""
        COPY (
            SELECT *
            FROM read_parquet('{SOURCE}')
            USING SAMPLE {SAMPLE_ROWS} ROWS
        )
        TO '{OUT_CSV}'
        (FORMAT CSV, HEADER TRUE)
    """)

    row_count = conn.execute(f"SELECT COUNT(*) FROM read_csv_auto('{OUT_CSV}')").fetchone()[0]
    size_kb = OUT_CSV.stat().st_size // 1024

    print(f"✓ Sample written: {OUT_CSV}")
    print(f"  Rows : {row_count:,}")
    print(f"  Size : {size_kb:,} KB")
    conn.close()


if __name__ == "__main__":
    main()
