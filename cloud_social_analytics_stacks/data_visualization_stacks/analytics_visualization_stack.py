from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_lambda as _lambda,
    Duration,
    aws_s3 as s3
)
from constructs import Construct


class AnalyticsVisualizationStack(Stack):

    def __init__(self, scope: Construct, id: str, data_lake: s3.IBucket, **kwargs):
        super().__init__(scope, id, **kwargs)

        vpc = ec2.Vpc(
            self,
            "AnalyticsVpc",
            max_azs=2,
            nat_gateways=0
        )

        sg = ec2.SecurityGroup(
            self,
            "AnalyticsInstanceSG",
            vpc=vpc,
            allow_all_outbound=True
        )

        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(22))
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(8088))
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(5432))

        role = iam.Role(
            self,
            "LambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com")
        )

        role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        )

        data_lake.grant_read(role)

        role.add_to_policy(iam.PolicyStatement(
            actions=["ec2:DescribeInstances"],
            resources=["*"]
        ))

        db_layer = _lambda.LayerVersion(
            self,
            "AnalyticsDbLayer",
            code=_lambda.Code.from_asset("layers/analytics-db"),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_11]
        )

        user_data = ec2.UserData.for_linux()

        user_data.add_commands(
            "yum update -y",
            "yum install -y docker",
            "service docker start",
            "usermod -a -G docker ec2-user",
            "curl -L https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m) -o /usr/local/bin/docker-compose",
            "chmod +x /usr/local/bin/docker-compose",

            "mkdir -p /opt/analytics",
            "cd /opt/analytics",

            "cat <<EOF > docker-compose.yml\nversion: '3.8'\nservices:\n  postgres:\n    image: postgres:15\n    environment:\n      POSTGRES_USER: admin\n      POSTGRES_PASSWORD: admin123\n      POSTGRES_DB: analytics\n    ports:\n      - '5432:5432'\n    volumes:\n      - pgdata:/var/lib/postgresql/data\n  superset:\n    image: apache/superset:latest\n    container_name: superset_app\n    ports:\n      - '8088:8088'\n    environment:\n      SUPERSET_SECRET_KEY: 'my_secret_key'\n    depends_on:\n      - postgres\nvolumes:\n  pgdata:\nEOF",
            "docker-compose up -d",

            "sleep 60",
            "docker exec -u root superset_app sh -lc '/app/.venv/bin/python -m ensurepip --upgrade || true; /app/.venv/bin/python -m pip install --no-cache-dir psycopg2-binary pg8000'",
            "docker exec superset_app superset db upgrade",
            "docker exec superset_app superset fab create-admin --username admin --firstname admin --lastname admin --email admin@local.com --password admin",
            "docker exec superset_app superset init"
        )

        instance = ec2.Instance(
            self,
            "AnalyticsInstanceV2",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3,
                ec2.InstanceSize.MICRO
            ),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            security_group=sg,
            user_data=user_data,
        )

        _lambda.Function(
            self,
            "GoldToPostgresLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_incremental_handler.lambda_handler",
            code=_lambda.Code.from_asset("lambdas/analyticsVisualization"),
            layers=[
                db_layer,
                _lambda.LayerVersion.from_layer_version_arn(
                    self,
                    "AwsSdkPandasLayer",
                    "arn:aws:lambda:eu-central-1:336392948345:layer:AWSSDKPandas-Python311:21"
                )
            ],
            timeout=Duration.minutes(10),
            memory_size=1024,
            role=role,
            environment={
                "S3_BUCKET": data_lake.bucket_name,
                "S3_PREFIX": "gold/",
                "PG_CONN": f"postgresql+pg8000://admin:admin123@{instance.instance_public_dns_name}:5432/analytics"
            }
        )