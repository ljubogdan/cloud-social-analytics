from aws_cdk import (
    Stack,
    aws_lambda as _lambda,
    aws_iam as iam,
    Duration,
    Size,
)
from constructs import Construct

class TwitterPostsSilverStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, data_bucket, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        role = iam.Role(
            self,
            "TwitterPostsSilverRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )
        
        role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"))
        data_bucket.grant_read(role, "bronze/twitter/*")
        data_bucket.grant_write(role, "silver/posts/*")

        wrangler_layer = _lambda.LayerVersion.from_layer_version_arn(
            self,
            "WranglerLayer",
            "arn:aws:lambda:eu-central-1:336392948345:layer:AWSSDKPandas-Python312:1"
        )

        self.fn = _lambda.Function(
            self,
            "TwitterPostsSilverLambda",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="twitter_posts_extraction.handler",
            code=_lambda.Code.from_asset("lambdas/twitterPostsExtraction"),
            role=role,
            timeout=Duration.minutes(15),
            memory_size=3008, 
            ephemeral_storage_size=Size.gibibytes(10),
            environment={
                "BUCKET_NAME": data_bucket.bucket_name,
            },
            layers=[wrangler_layer],
        )