from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_secretsmanager as secretsmanager
)
from constructs import Construct

class AnalyticsVisualizationStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)
        
        vpc = ec2.Vpc.from_lookup(self, "DefaultVpc", is_default=True)

        ec2_sg = ec2.SecurityGroup(self, "PostgresSG", vpc=vpc, allow_all_outbound=True)
        
        # TODO: Add security group rules to allow Lambda to connect to Postgres
        ec2_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(5432), "Allow Postgres access from Lambda")

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
            instance_type=ec2.InstanceType("t3.medium"),
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
            
            f"SECRET_JSON=$(aws secretsmanager get-secret-value --secret-id {db_secret.secret_arn} --region {self.region} --query SecretString --output text)",
            "DB_PASSWORD=$(echo $SECRET_JSON | jq -r .password)",
            
            "cat <<EOF > /home/ec2-user/docker-compose.yml",
            "version: '3.8'",
            "services:",
            "  db:",
            "    image: postgres:15-alpine",
            "    container_name: postgres-db",
            "    restart: always",
            "    environment:",
            "      POSTGRES_DB: socialanalytics",
            "      POSTGRES_USER: admin",
            "      POSTGRES_PASSWORD: \$DB_PASSWORD",
            "    ports:",
            "      - '5432:5432'",
            "",
            "  superset:",
            "    image: apache/superset:latest",
            "    container_name: superset-app",
            "    restart: always",
            "    ports:",
            "      - '8088:8088'",
            "    environment:",
            "      - SUPERSET_SECRET_KEY=long-random-secret-key-change-me",
            "      - DATABASE_URL=postgresql://admin:\$DB_PASSWORD@db:5432/socialanalytics",
            "EOF",
            
            "cd /home/ec2-user",
            "docker-compose up -d"
        )