import awswrangler as wr
import os

def lambda_handler(event, context):
    con = wr.postgresql.connect("POSTGRES_CONNECTION_STRING")
    
    s3_path = "s3://social-medias/silver/metrics/"
    
    df = wr.s3.read_parquet(path=s3_path)
    
    wr.postgresql.to_sql(
        df=df,
        table="metrics_table",
        con=con,
        schema="public",
        mode="append"
    )
    
    con.close()
    return {"status": "success"}