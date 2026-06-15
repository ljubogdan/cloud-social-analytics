import os
import pandas as pd
import awswrangler as wr
from datetime import datetime, timezone, timedelta

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

def compute_dq_chunked(path, filters=None, max_rows=50000):
    total_rows = 0
    total_cells = 0
    non_null_cells = 0
    try:
        chunks = wr.s3.read_parquet(
            path=path,
            dataset=True,
            chunked=True,
            filters=filters
        )
        for chunk in chunks:
            rows, cols = chunk.shape
            total_rows += rows
            total_cells += rows * cols
            non_null_cells += int(chunk.notna().sum().sum())
            if total_rows >= max_rows:
                break
    except Exception:
        return total_rows, 0.0
    dq_score = round((non_null_cells / total_cells * 100), 2) if total_cells > 0 else 0.0
    return total_rows, dq_score

def handler(event, context):
    daily_counts = {}
    top_candidates = []
    try:
        chunks = wr.s3.read_parquet(
            path=f"s3://{BUCKET_NAME}/silver/users/platform=X/",
            dataset=True,
            chunked=True,
            columns=["username", "created_at", "followers_count"]
        )
        for chunk in chunks:
            chunk["date"] = chunk["created_at"].dt.date.astype(str)
            for dv, cnt in chunk["date"].value_counts().items():
                daily_counts[dv] = daily_counts.get(dv, 0) + cnt
            if "followers_count" in chunk.columns:
                f = chunk[chunk["followers_count"].notna()]
                if not f.empty:
                    top_candidates.append(f[["username", "followers_count"]].nlargest(10, "followers_count"))
    except Exception:
        pass

    if daily_counts:
        du = pd.DataFrame(list(daily_counts.items()), columns=["date", "new_users"]).sort_values("date")
        du["total_users"] = du["new_users"].cumsum()
        du["platform"] = "X"
        write_gold(du, f"s3://{BUCKET_NAME}/gold/daily_users_metric/", ["platform", "date"])

    if top_candidates:
        tf = pd.concat(top_candidates, ignore_index=True).nlargest(10, "followers_count").reset_index(drop=True)
        tf["rank"] = tf.index + 1
        tf["snapshot_date"] = TODAY
        write_gold(tf, f"s3://{BUCKET_NAME}/gold/top_twitter_users_by_followers/", ["snapshot_date"])

    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    pf = [("year", "==", int(yesterday.year)), ("month", "==", int(yesterday.month)), ("day", "==", int(yesterday.day))]

    tables = {
        "silver_posts": (f"s3://{BUCKET_NAME}/silver/posts/", pf),
        "silver_hn_users": (f"s3://{BUCKET_NAME}/silver/users/platform=HackerNews/", None),
        "silver_twitter_users": (f"s3://{BUCKET_NAME}/silver/users/platform=X/", None),
    }

    rows = []
    for tn, (p, f) in tables.items():
        tr, ds = compute_dq_chunked(p, filters=f)
        rows.append({"table_name": tn, "total_rows": tr, "non_null_pct": ds, "snapshot_date": TODAY})

    write_gold(pd.DataFrame(rows), f"s3://{BUCKET_NAME}/gold/data_quality_score/", ["snapshot_date"])
    return {"status": "Completed", "snapshot_date": TODAY}
