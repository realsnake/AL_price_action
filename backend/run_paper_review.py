from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from services.paper_review import default_review_session_date, write_daily_paper_review


REPO_ROOT = Path(__file__).resolve().parents[1]
SESSION_DATE = os.getenv("PAPER_REVIEW_DATE", "").strip() or None
OUTPUT_ROOT = os.getenv("PAPER_REVIEW_OUTPUT_ROOT", "reports/paper_reviews")
REFRESH_LIMIT = int(os.getenv("PAPER_REVIEW_REFRESH_LIMIT", "500"))


def _resolve_output_root(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


async def main() -> None:
    review_date = SESSION_DATE or default_review_session_date()
    result = await write_daily_paper_review(
        session_date=review_date,
        output_root=_resolve_output_root(OUTPUT_ROOT),
        refresh_limit=REFRESH_LIMIT,
    )
    print(
        json.dumps(
            {
                "session_date": result.session_date,
                "trade_count": result.trade_count,
                "filled_trade_count": result.filled_trade_count,
                "realized_pnl": result.realized_pnl,
                "recommendation": result.recommendation,
                "output_dir": str(result.output_dir.resolve()),
                "review_md": str(result.markdown_path.resolve()),
                "review_json": str(result.json_path.resolve()),
                "trades_csv": str(result.trades_csv_path.resolve()),
                "round_trips_csv": str(result.round_trips_csv_path.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
