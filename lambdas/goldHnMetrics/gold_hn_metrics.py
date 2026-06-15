import os
import pandas as pd
import awswrangler as wr
from datetime import datetime, timezone, timedelta, date as date_type

BUCKET_NAME = os.environ["BUCKET_NAME"]
HN_POST_TYPES = {"story", "comment", "ask_hn", "job", "poll"}

def get_target_date(event):
    try:
        detail = event.get("detail", {})
        return date_type(int(detail["year"]), int(detail["month"]), int(detail["day"]))
    except Exception:
        return datetime.now(timezone.utc).date() - timedelta(days=1)

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

def top_n_largest_chunked(path, row_filter, sort_col, n, select_cols, filters=None):
    try:
        chunks = wr.s3.read_parquet(
            path=path, 
            dataset=True, 
            chunked=True, 
            filters=filters
        )
    except Exception:
        return pd.DataFrame()

    candidates = []
    for chunk in chunks:
        if sort_col not in chunk.columns:
            continue
        for col, val in row_filter.items():
            if col in chunk.columns:
                chunk = chunk[chunk[col] == val]
        chunk = chunk[chunk[sort_col].notna()]
        if chunk.empty:
            continue
        available_cols = [c for c in select_cols if c in chunk.columns]
        candidates.append(chunk[available_cols].nlargest(n, sort_col))

    if not candidates:
        return pd.DataFrame()

    result = pd.concat(candidates, ignore_index=True).nlargest(n, sort_col).reset_index(drop=True)
    result["rank"] = result.index + 1
    return result

def handler(event, context):
    target = get_target_date(event)
    snapshot_date = str(target)
    
    y, m, d = int(target.year), int(target.month), int(target.day)

    try:
        chunks = wr.s3.read_parquet(
            path=f"s3://{BUCKET_NAME}/silver/posts/",
            dataset=True,
            chunked=True,
            filters=[("year", "==", y), ("month", "==", m), ("day", "==", d)]
        )
        daily_counts = {}
        for chunk in chunks:
            hn_chunk = chunk[chunk["post_type"].isin(HN_POST_TYPES)]
            for pt, cnt in hn_chunk["post_type"].value_counts().items():
                daily_counts[pt] = daily_counts.get(pt, 0) + cnt
    except Exception:
        daily_counts = {}

    if daily_counts:
        agg = pd.DataFrame(list(daily_counts.items()), columns=["post_type", "count"])
        agg["date"] = snapshot_date
        write_gold(agg, f"s3://{BUCKET_NAME}/gold/daily_hn_posts_metric/", ["date"])

    try:
        hn_users = wr.s3.read_parquet(
            path=f"s3://{BUCKET_NAME}/silver/users/platform=HackerNews/",
            dataset=True
        )
    except Exception:
        hn_users = pd.DataFrame()

    if not hn_users.empty:
        hn_users["date"] = hn_users["created_at"].dt.date.astype(str)
        daily_hn_users = (
            hn_users.groupby("date").size()
            .reset_index(name="new_users")
            .sort_values("date")
        )
        daily_hn_users["total_users"] = daily_hn_users["new_users"].cumsum()
        daily_hn_users["platform"] = "HackerNews"
        write_gold(daily_hn_users, f"s3://{BUCKET_NAME}/gold/daily_users_metric/", ["platform", "date"])

    if not hn_users.empty:
        top_high = (
            hn_users[hn_users["karma_score"].notna()]
            .nlargest(10, "karma_score")[["username", "karma_score"]]
            .reset_index(drop=True)
        )
        top_high["rank"] = top_high.index + 1
        top_high["snapshot_date"] = snapshot_date
        write_gold(top_high, f"s3://{BUCKET_NAME}/gold/top_hn_users_high_karma/", ["snapshot_date"])

    if not hn_users.empty:
        bottom_karma = (
            hn_users[hn_users["karma_score"].notna()]
            .nsmallest(10, "karma_score")[["username", "karma_score"]]
            .reset_index(drop=True)
        )
        bottom_karma["rank"] = bottom_karma.index + 1
        bottom_karma["snapshot_date"] = snapshot_date
        write_gold(bottom_karma, f"s3://{BUCKET_NAME}/gold/top_hn_users_low_karma/", ["snapshot_date"])

    top_jobs = top_n_largest_chunked(
        path=f"s3://{BUCKET_NAME}/silver/posts/",
        row_filter={"post_type": "job"},
        sort_col="score",
        n=10,
        select_cols=["post_id", "author_username", "content_text", "score"],
        filters=[("year", "==", y)]
    )
    if not top_jobs.empty:
        top_jobs["snapshot_date"] = snapshot_date
        write_gold(top_jobs, f"s3://{BUCKET_NAME}/gold/top_hn_jobs_by_score/", ["snapshot_date"])

    top_stories = top_n_largest_chunked(
        path=f"s3://{BUCKET_NAME}/silver/posts/",
        row_filter={"post_type": "story"},
        sort_col="score",
        n=10,
        select_cols=["post_id", "author_username", "content_text", "score"],
        filters=[("year", "==", y)]
    )
    if not top_stories.empty:
        top_stories["snapshot_date"] = snapshot_date
        write_gold(top_stories, f"s3://{BUCKET_NAME}/gold/top_hn_posts_by_score/", ["snapshot_date"])

    return {"status": "Completed", "snapshot_date": snapshot_date}
