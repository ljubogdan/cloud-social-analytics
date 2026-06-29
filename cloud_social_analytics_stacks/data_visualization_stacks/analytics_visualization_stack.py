from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    RemovalPolicy
)
from constructs import Construct

class AnalyticsVisualizationStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)
        
        vpc = ec2.Vpc.from_lookup(self, "DefaultVpc", is_default=True)

        ec2_sg = ec2.SecurityGroup(self, "PostgresSG", vpc=vpc, allow_all_outbound=True)
        
        # TODO: Add security group rules to allow Lambda to connect to Postgres
        ec2_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(5432), "Allow Postgres access from Lambda")

        role = iam.Role(self, "InstanceRole", assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"))
        role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"))

        instance = ec2.Instance(self, "PostgresInstance",
            instance_type=ec2.InstanceType("t3.small"),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            vpc=vpc,
            security_group=ec2_sg,
            role=role
        )

        instance.add_user_data(
            "yum update -y",
            "yum install -y docker",
            "systemctl start docker",
            "systemctl enable docker",
            "usermod -a -G docker ec2-user",
            # Run Postgres container
            "docker run -d --name postgres-db "
            "-e POSTGRES_USER=admin "
            "-e POSTGRES_PASSWORD=tajna_lozinka "
            "-e POSTGRES_DB=socialanalytics "
            "-p 5432:5432 "
            "--restart always "
            "postgres:15-alpine"
        )