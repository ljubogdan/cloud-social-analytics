import os
import pandas as pd
import awswrangler as wr
from datetime import datetime, timezone

BUCKET_NAME = os.environ["BUCKET_NAME"]
TODAY = str(datetime.now(timezone.utc).date())


def write_gold(df, path, partition_cols):
    if df.empty:
        return
    wr.s3.to_parquet(
        df=df,
        path=path,
        dataset=True,
        mode="overwrite_partitions",
        partition_cols=partition_cols
    )


def compute_dq_chunked(path):
    """Računa Data Quality Score za jednu tabelu čitajući u chunk-ovima."""
    total_rows = 0
    total_cells = 0
    non_null_cells = 0

    try:
        chunks = wr.s3.read_parquet(path=path, dataset=True, chunked=True)
        for chunk in chunks:
            rows, cols = chunk.shape
            total_rows += rows
            total_cells += rows * cols
            non_null_cells += int(chunk.notna().sum().sum())
    except Exception:
        return total_rows, 0.0

    dq_score = round((non_null_cells / total_cells * 100), 2) if total_cells > 0 else 0.0
    return total_rows, dq_score


def handler(event, context):

    # 1. Dnevni broj Twitter korisnika — chunked jer može biti puno unique usera
    daily_counts = {}
    try:
        chunks = wr.s3.read_parquet(
            path=f"s3://{BUCKET_NAME}/silver/users/platform=X/",
            dataset=True,
            chunked=True
        )
        for chunk in chunks:
            chunk["date"] = chunk["created_at"].dt.date.astype(str)
            for date_val, cnt in chunk["date"].value_counts().items():
                daily_counts[date_val] = daily_counts.get(date_val, 0) + cnt
    except Exception:
        daily_counts = {}

    if daily_counts:
        daily_users = (
            pd.DataFrame(list(daily_counts.items()), columns=["date", "new_users"])
            .sort_values("date")
        )
        daily_users["total_users"] = daily_users["new_users"].cumsum()
        daily_users["platform"] = "X"
        write_gold(daily_users, f"s3://{BUCKET_NAME}/gold/daily_users_metric/", ["platform", "date"])

    # 2. Top 10 Twitter korisnika po broju pratilaca — chunked
    top_candidates = []
    try:
        chunks = wr.s3.read_parquet(
            path=f"s3://{BUCKET_NAME}/silver/users/platform=X/",
            dataset=True,
            chunked=True
        )
        for chunk in chunks:
            if "followers_count" not in chunk.columns:
                continue
            chunk = chunk[chunk["followers_count"].notna()]
            if chunk.empty:
                continue
            top_candidates.append(
                chunk[["username", "followers_count"]].nlargest(10, "followers_count")
            )
    except Exception:
        top_candidates = []

    if top_candidates:
        top_followers = (
            pd.concat(top_candidates, ignore_index=True)
            .nlargest(10, "followers_count")
            .reset_index(drop=True)
        )
        top_followers["rank"] = top_followers.index + 1
        top_followers["snapshot_date"] = TODAY
        write_gold(
            top_followers,
            f"s3://{BUCKET_NAME}/gold/top_twitter_users_by_followers/",
            ["snapshot_date"]
        )

    # 3. Data Quality Score za sve silver tabele — chunked
    silver_tables = {
        "silver_posts": f"s3://{BUCKET_NAME}/silver/posts/",
        "silver_hn_users": f"s3://{BUCKET_NAME}/silver/users/platform=HackerNews/",
        "silver_twitter_users": f"s3://{BUCKET_NAME}/silver/users/platform=X/",
    }

    dq_rows = []
    for table_name, path in silver_tables.items():
        total_rows, dq_score = compute_dq_chunked(path)
        dq_rows.append({
            "table_name": table_name,
            "total_rows": total_rows,
            "non_null_pct": dq_score,
            "snapshot_date": TODAY
        })

    dq_df = pd.DataFrame(dq_rows)
    write_gold(dq_df, f"s3://{BUCKET_NAME}/gold/data_quality_score/", ["snapshot_date"])

    return {"status": "Completed", "snapshot_date": TODAY}
