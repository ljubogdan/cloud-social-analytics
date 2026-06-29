from aws_cdk import (
    Size,
    Stack,
    aws_lambda as _lambda,
    aws_iam as iam,
    Duration,
    aws_events as events,
    aws_events_targets as targets,
)
from constructs import Construct

class HackerNewsUsersSilverStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, data_bucket, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        role = iam.Role(
            self,
            "HackerNewsUsersSilverRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )

        role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        )

        data_bucket.grant_read(role)
        data_bucket.grant_write(role, "silver/users/*")

        wrangler_layer = _lambda.LayerVersion.from_layer_version_arn(
            self,
            "WranglerLayer",
            "arn:aws:lambda:eu-central-1:336392948345:layer:AWSSDKPandas-Python312:1"
        )

        self.fn = _lambda.Function(
            self,
            "HackerNewsUsersSilverLambda",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="hacker_news_users_extraction.handler",
            code=_lambda.Code.from_asset("lambdas/hackerNewsUsersExtraction"),
            role=role,
            timeout=Duration.minutes(15),
            memory_size=3007,
            ephemeral_storage_size=Size.gibibytes(10),
            environment={
                "BUCKET_NAME": data_bucket.bucket_name,
            },
            layers=[wrangler_layer],
        )

        events.Rule(
            self,
            "HackerNewsUsersTrigger",
            event_pattern=events.EventPattern(
                source=["socialanalytics.hackernews"],
                detail_type=["HackerNewsIngestionCompleted"]
            ),
            targets=[
                targets.LambdaFunction(self.fn)
            ]
        )

