from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_secretsmanager as secretsmanager,
    aws_lambda as _lambda,
    Duration,
    BundlingOptions
)
from constructs import Construct

class AnalyticsVisualizationStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        
        vpc = ec2.Vpc.from_lookup(self, "DefaultVpc", is_default=True)

        ec2.GatewayVpcEndpoint(
            self,
            "S3Endpoint",
            vpc=vpc,
            service=ec2.GatewayVpcEndpointAwsService.S3
        )

        ec2_sg = ec2.SecurityGroup(self, "PostgresSG", vpc=vpc, allow_all_outbound=True)
        lambda_sg = ec2.SecurityGroup(self, "LambdaSG", vpc=vpc, allow_all_outbound=True)

        ec2_sg.add_ingress_rule(lambda_sg, ec2.Port.tcp(5432), "Allow Lambda to access Postgres")

        db_secret = secretsmanager.Secret(self, "PostgresPasswordSecret",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username": "admin"}',
                generate_string_key="password",
                password_length=16
            )
        )        

        role = iam.Role(self, "InstanceRole", assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"))
        
        role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"))
        
        role.add_to_policy(iam.PolicyStatement(
            actions=["secretsmanager:GetSecretValue"],
            resources=[db_secret.secret_arn]
        ))

        instance = ec2.Instance(self, "PostgresInstance",
            instance_type=ec2.InstanceType("t3.micro"),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            vpc=vpc,
            security_group=ec2_sg,
            role=role
        )

        instance.add_user_data(
            "#!/bin/bash",
            "yum update -y",
            "yum install -y docker jq",
            "systemctl start docker",
            "systemctl enable docker",
            "usermod -a -G docker ec2-user",
            
            "curl -L https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 -o /usr/local/bin/docker-compose",
            "chmod +x /usr/local/bin/docker-compose",
            
            # f"SECRET_JSON=$(aws secretsmanager get-secret-value --secret-id {db_secret.secret_arn} --region {self.region} --query SecretString --output text)",
            #"DB_PASSWORD=$(echo $SECRET_JSON | jq -r .password)",
            "DB_PASSWORD=mypassword123",

            r"cat <<EOF > /home/ec2-user/docker-compose.yml",
            "version: '3.8'",
            "services:",
            "  db:",
            "    image: postgres:15-alpine",
            "    container_name: postgres-db",
            "    restart: always",
            "    environment:",
            "      POSTGRES_DB: socialanalytics",
            "      POSTGRES_USER: admin",
            r"      POSTGRES_PASSWORD: mypassword123",
            "    ports:",
            "      - '5432:5432'",
            "    healthcheck:",
            "      test: ['CMD-SHELL', 'pg_isready -U admin']",
            "      interval: 5s",
            "      timeout: 5s",
            "      retries: 5",
            "",
            "  superset:",
            "    image: apache/superset:latest",
            "    container_name: superset-app",
            "    restart: always",
            "    ports:",
            "      - '8088:8088'",
            "    environment:",
            "      - SUPERSET_SECRET_KEY=long-random-secret-key-change-me",
            r"      - DATABASE_URL=postgresql://admin:$DB_PASSWORD@db:5432/socialanalytics",
            "EOF",
            
            "cd /home/ec2-user",
            "docker-compose up -d"
        )
 
        lambda_role = iam.Role(
            self, "LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com")
        )

        lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        )
 
        lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3ReadOnlyAccess")
        )
 
        db_secret.grant_read(lambda_role)
 
        lambda_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "ec2:CreateNetworkInterface",
                "ec2:DescribeNetworkInterfaces",
                "ec2:DeleteNetworkInterface"
            ],
            resources=["*"]
        ))
 
        _lambda.Function(
            self,
            "PostgresLoaderLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_incremental_handler.lambda_incremental_postgres_handler",
            code=_lambda.Code.from_asset(
                "lambdas/analyticsVisualization",
                bundling=BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_11.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "cp -au . /asset-output"
                    ]
                )
            ),
            layers=[
                _lambda.LayerVersion.from_layer_version_arn(
                    self,
                    "AwsWranglerLayer",
                    f"arn:aws:lambda:{self.region}:336392948345:layer:AWSSDKPandas-Python311:20"
                )
            ],
            #vpc=vpc,
            allow_public_subnet=True,
            #security_groups=[lambda_sg],
            timeout=Duration.minutes(15),
            memory_size=1024,
            role=lambda_role,
            environment={
                "DB_HOST": instance.instance_private_ip,
                "DB_USER": "admin",
                "DB_NAME": "socialanalytics",
                "BUCKET_NAME": "data-lake-bucket-social-analytics",
                "SECRET_ARN": db_secret.secret_arn,
                "DB_PASSWORD": "mypassword123"
            }
        )