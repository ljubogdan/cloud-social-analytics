import awswrangler as wr
import os
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger()
logger.setLevel(logging.INFO)
print(os.listdir("/var/task"))

def lambda_incremental_postgres_handler(event, context):
    logger.info("START LAMBDA")

    try:
        con = wr.postgresql.connect(
            host=os.environ["DB_HOST"],
            database=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            port=5432
        )

        yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).strftime('%Y-%m-%d')

        partitioned_folders = {
            "daily_hn_posts_metric",
            "top_hn_users_high_karma",
            "top_hn_users_low_karma",
            "top_hn_posts_by_score",
            "top_hn_jobs_by_score",
            "data_quality_score"
        }

        mapping = {
            "daily_hn_posts_metric": "hn_daily_posts",
            "top_hn_users_high_karma": "hn_top_users_karma",
            "top_hn_users_low_karma": "hn_bottom_users_karma",
            "top_hn_posts_by_score": "hn_top_posts_score",
            "top_hn_jobs_by_score": "hn_top_jobs_score",
            "data_quality_score": "data_quality_report"
        }

        bucket_name = os.environ["BUCKET_NAME"]

        successful_tables = []
        failed_tables = []

        for folder, table in mapping.items():
            try:
                base_path = f"s3://{bucket_name}/gold/{folder}/"

                if folder in partitioned_folders:
                    base_path += f"snapshot_date={yesterday}/"

                df = wr.s3.read_parquet(path=base_path)

                logger.info(f"FOLDER: {folder}")
                logger.info(f"BASE PATH: {base_path}")

                if df is None or df.empty:
                    failed_tables.append(f"{folder} - empty")
                    continue

                possible_keys = ["id", "post_id", "user_id", "username"]
                subset_cols = [c for c in possible_keys if c in df.columns]

                if subset_cols:
                    df = df.drop_duplicates(subset=subset_cols, keep="last")
                    mode = "upsert"
                else:
                    df = df.drop_duplicates(keep="last")
                    subset_cols = None
                    mode = "append"

                wr.postgresql.to_sql(
                    df=df,
                    con=con,
                    table=table,
                    schema="public",
                    mode=mode,
                    upsert_conflict_columns=subset_cols
                )

                successful_tables.append(table)

            except Exception as e:
                failed_tables.append(f"{folder} - {str(e)}")
                continue

        con.close()

        return {
            "statusCode": 200,
            "status": "completed",
            "successful_tables": successful_tables,
            "failed_tables": failed_tables,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "status": "failed",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }