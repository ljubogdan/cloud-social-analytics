from aws_cdk import Stack, aws_s3 as s3, RemovalPolicy
from aws_cdk.aws_s3 import BucketEncryption
from constructs import Construct

class DataStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.data_lake = s3.Bucket(
            self,
            "DataLake",
            bucket_name = "data-lake-bucket-social-analytics",
            encryption = BucketEncryption.S3_MANAGED,
            versioned = True,
            removal_policy = RemovalPolicy.RETAIN
        )