import os
import uuid
import boto3
import pandas as pd
import awswrangler as wr

BUCKET_NAME = os.environ["BUCKET_NAME"]
s3 = boto3.client("s3")

def handler(event, context):
    prefix = "bronze/twitter/"
    
    response = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix)
    
    if "Contents" not in response:
        return {"status": "No files to process"}

    seen_users = set()

    for obj in response["Contents"]:
        key = obj["Key"]
        
        if key.endswith(".csv"):
            print(f"Processing: {key}")
            
            s3_path = f"s3://{BUCKET_NAME}/{key}"
            reader = wr.s3.read_csv(
                path=s3_path,
                usecols=["user_name", "user_verified", "user_created"],
                chunksize=100000,
                dataset=False
            )


            for chunk in reader:

                chunk = chunk[
                    ~chunk["user_name"].isin(seen_users)
                ]

                seen_users.update(chunk["user_name"])

                if chunk.empty:
                    continue
                
                created_at_series = pd.to_datetime(chunk["user_created"], errors="coerce", utc=True)

                users_df = pd.DataFrame({
                    "user_id": chunk["user_name"].apply(
                        lambda u: str(uuid.uuid5(uuid.NAMESPACE_DNS, f"X:{u}"))
                    ),
                    "username": chunk["user_name"],
                    "platform": "X",
                    "karma_score": None,
                    "is_verified": chunk["user_verified"].astype(bool),
                    "created_at": created_at_series
                })
                
                users_df = users_df.dropna(subset=["created_at"])
    
                if users_df.empty:
                    continue

                wr.s3.to_parquet(
                    df=users_df,
                    path=f"s3://{BUCKET_NAME}/silver/users/",
                    dataset=True,
                    mode="append",
                    partition_cols=["platform"]
                )
                
    return {"status": "Completed"}