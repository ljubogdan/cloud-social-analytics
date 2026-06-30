import awswrangler as wr
import os
from datetime import datetime, timezone, timedelta

def lambda_incremental_postgres_handler(event, context):
    con = wr.postgresql.connect(
        host=os.environ['DB_HOST'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASS'],
        database=os.environ['DB_NAME']
    )

    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    partitioned_folders = [
        "daily_hn_posts_metric", 
        "top_hn_users_high_karma", 
        "top_hn_users_low_karma", 
        "top_hn_posts_by_score",
        "top_hn_jobs_by_score",
        "data_quality_score"
    ]

    mapping = {
        "daily_hn_posts_metric": "hn_daily_posts",
        "daily_users_metric": "daily_users",
        "top_hn_users_high_karma": "hn_top_users_karma",
        "top_hn_users_low_karma": "hn_bottom_users_karma",
        "top_hn_posts_by_score": "hn_top_posts_score",
        "top_hn_jobs_by_score": "hn_top_jobs_score",
        "top_twitter_users_by_followers": "twitter_top_users",
        "data_quality_score": "data_quality_report"
    }
    
    for folder, table in mapping.items():
        if folder in partitioned_folders:
            base_path = f"s3://{os.environ['BUCKET_NAME']}/gold/{folder}/snapshot_date={yesterday}/"
        else:
            base_path = f"s3://{os.environ['BUCKET_NAME']}/gold/{folder}/"
        
        try:
            if not wr.s3.does_object_exist(base_path):
                print(f"Skipping: {base_path} does not exist.")
                continue
                
            df = wr.s3.read_parquet(path=base_path)
            
            subset_cols = [c for c in ['id', 'post_id', 'user_id', 'username'] if c in df.columns]
            df = df.drop_duplicates(subset=subset_cols if subset_cols else None)
            
            wr.postgresql.to_sql(
                df=df,
                table=table,
                con=con,
                schema="public",
                mode="upsert",
                upsert_conflict_columns=subset_cols if subset_cols else ['id']
            )
            print(f"Success: {table} from {base_path}")
            
        except Exception as e:
            print(f"Error processing {folder}: {e}")
            
    con.close()
    return {"status": "success"}