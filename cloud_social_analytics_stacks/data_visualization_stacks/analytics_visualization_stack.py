from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_secretsmanager as secretsmanager,
    BundlingOptions,
    Duration,
    aws_s3 as s3,
)
from constructs import Construct


class AnalyticsVisualizationStack(Stack):

    def __init__(self, scope: Construct, id: str, data_lake: s3.IBucket, **kwargs):
        super().__init__(scope, id, **kwargs)

        # -----------------------------------------------------------------
        # VPC
        # Eksplicitno pravimo Public (za EC2/Superset) i Private-Isolated
        # (za Lambdu) subnet. Bez NAT gateway-a (nat_gateways=0), zato
        # Lambda dobija pristup S3-u preko Gateway Endpoint-a, ne preko
        # javnog interneta.
        # -----------------------------------------------------------------
        vpc = ec2.Vpc(
            self,
            "AnalyticsVpc",
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )

        # S3 Gateway Endpoint - besplatan, omogucava Lambdi (bez NAT-a) da
        # cita iz data lake bucketa
        vpc.add_gateway_endpoint(
            "S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
        )

        # -----------------------------------------------------------------
        # Kredencijali za Postgres - generisu se automatski, nigde u kodu
        # nema plain-text lozinke (original je imao "admin123" hardkodovano
        # na dva mesta)
        # -----------------------------------------------------------------
        db_secret = secretsmanager.Secret(
            self,
            "AnalyticsDbSecret",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username":"admin"}',
                generate_string_key="password",
                exclude_punctuation=True,
                password_length=24,
            ),
        )

        # -----------------------------------------------------------------
        # Security groups
        # -----------------------------------------------------------------
        ec2_sg = ec2.SecurityGroup(
            self,
            "AnalyticsInstanceSG",
            vpc=vpc,
            allow_all_outbound=True,
            description="SG za EC2 instancu sa Superset/Postgres",
        )

        lambda_sg = ec2.SecurityGroup(
            self,
            "AnalyticsLambdaSG",
            vpc=vpc,
            allow_all_outbound=True,
            description="SG za Lambda funkciju",
        )

        # Superset UI ostaje javan jer je to njegova namena.
        # Po potrebi ogranici na svoj IP/office CIDR umesto any_ipv4().
        ec2_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(8088), "Superset UI")

        # Postgres NIJE javan (original ga je izlagao celom internetu na 5432
        # sa hardkodovanom lozinkom). Sada je dozvoljen samo od Lambda SG-a.
        ec2_sg.add_ingress_rule(lambda_sg, ec2.Port.tcp(5432), "Postgres samo od Lambda funkcije")

        # SSH namerno NIJE otvoren nigde - pristup instanci ide preko
        # SSM Session Manager (vidi ec2_role ispod).

        # -----------------------------------------------------------------
        # IAM role
        # -----------------------------------------------------------------
        lambda_role = iam.Role(
            self,
            "LambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )
        lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        )
        # Lambda je sada u VPC-u pa joj treba i ova managed policy
        # (kreiranje/brisanje ENI-a) - u originalu je Lambda bila van VPC-a
        # pa ovo nije bilo potrebno.
        lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaVPCAccessExecutionRole"
            )
        )

        data_lake.grant_read(lambda_role)
        db_secret.grant_read(lambda_role)

        # Originalna "ec2:DescribeInstances" na resources=["*"] uklonjena -
        # Lambda handler koji je opisan (gold->postgres) ne treba EC2 API,
        # samo pristup S3-u i tajni sa kredencijalima. Vrati je ako je
        # handler stvarno koristi.

        ec2_role = iam.Role(
            self,
            "AnalyticsInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
        )
        # Omogucava SSM Session Manager pristup umesto javnog SSH-a (22)
        ec2_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "AmazonSSMManagedInstanceCore"
            )
        )
        db_secret.grant_read(ec2_role)

        # -----------------------------------------------------------------
        # EC2 UserData - PostgreSQL + Superset instalirani direktno na
        # instancu (bez Dockera), pokrenuti kao systemd servisi da rade
        # trajno (original je zavisio od "docker-compose up -d" i
        # "sleep 60" da bi kontejneri stigli da se podignu, sto je
        # nepouzdano).
        # -----------------------------------------------------------------
        user_data = ec2.UserData.for_linux()

        user_data.add_commands(
            "set -eux",
            "dnf update -y",
            "dnf install -y postgresql15 postgresql15-server postgresql15-contrib "
            "python3.11 python3.11-pip python3.11-devel gcc gcc-c++ make "
            "libffi-devel openssl-devel cyrus-sasl-devel openldap-devel jq",

            # --- Init i start Postgres ---
            "postgresql-setup --initdb",
            "systemctl enable postgresql",
            "systemctl start postgresql",

            # --- Kredencijali iz Secrets Manager (awscli je preinstaliran na AL2023) ---
            f"SECRET_JSON=$(aws secretsmanager get-secret-value "
            f"--secret-id {db_secret.secret_arn} --region {self.region} "
            f"--query SecretString --output text)",
            "DB_USER=$(echo \"$SECRET_JSON\" | jq -r .username)",
            "DB_PASS=$(echo \"$SECRET_JSON\" | jq -r .password)",

            "sudo -u postgres psql -v ON_ERROR_STOP=1 "
            "-c \"CREATE ROLE ${DB_USER} WITH LOGIN SUPERUSER PASSWORD '${DB_PASS}';\"",
            "sudo -u postgres psql -v ON_ERROR_STOP=1 -c \"CREATE DATABASE analytics OWNER ${DB_USER};\"",
            "sudo -u postgres psql -v ON_ERROR_STOP=1 -c \"CREATE DATABASE superset_meta OWNER ${DB_USER};\"",

            # --- Dozvoli konekcije sa Lambda SG-a (unutar VPC CIDR-a), ne sa celog interneta ---
            f"echo \"host all all {vpc.vpc_cidr_block} md5\" | sudo tee -a "
            "$(sudo -u postgres psql -tAc \"show hba_file;\")",
            "sudo sed -i \"s/^#listen_addresses.*/listen_addresses = '*'/\" "
            "$(sudo -u postgres psql -tAc \"show config_file;\")",
            "systemctl restart postgresql",

            # --- Superset u virtualnom okruzenju (bez Dockera) ---
            "python3.11 -m venv /opt/superset-venv",
            "/opt/superset-venv/bin/pip install --upgrade pip",
            "/opt/superset-venv/bin/pip install apache-superset psycopg2-binary gunicorn",

            "mkdir -p /etc/superset",
            "SUPERSET_SECRET=$(openssl rand -base64 42)",
            "cat > /etc/superset/superset_config.py <<EOF\n"
            "SECRET_KEY = '${SUPERSET_SECRET}'\n"
            "SQLALCHEMY_DATABASE_URI = 'postgresql+psycopg2://${DB_USER}:${DB_PASS}@localhost/superset_meta'\n"
            "EOF",

            "export SUPERSET_CONFIG_PATH=/etc/superset/superset_config.py",
            "export FLASK_APP=superset",
            "/opt/superset-venv/bin/superset db upgrade",
            "/opt/superset-venv/bin/superset fab create-admin "
            "--username admin --firstname admin --lastname admin "
            "--email admin@local.com --password \"${DB_PASS}\"",
            "/opt/superset-venv/bin/superset init",

            # --- Automatska registracija 'analytics' baze (KPI/metrike) kao
            # Superset data source-a, da niko rucno ne mora da je dodaje
            # kroz UI (Settings -> Database Connections) ---
            "/opt/superset-venv/bin/superset set-database-uri "
            "--database_name \"AnalyticsDB\" "
            "--uri \"postgresql+psycopg2://${DB_USER}:${DB_PASS}@localhost/analytics\"",

            # --- systemd servis, da Superset radi trajno i preÅ¾ivi reboot ---
            "cat > /etc/systemd/system/superset.service <<EOF\n"
            "[Unit]\n"
            "Description=Apache Superset\n"
            "After=network.target postgresql.service\n\n"
            "[Service]\n"
            "Environment=SUPERSET_CONFIG_PATH=/etc/superset/superset_config.py\n"
            "ExecStart=/opt/superset-venv/bin/gunicorn -w 4 -b 0.0.0.0:8088 'superset.app:create_app()'\n"
            "Restart=always\n"
            "User=root\n\n"
            "[Install]\n"
            "WantedBy=multi-user.target\n"
            "EOF",
            "systemctl daemon-reload",
            "systemctl enable superset",
            "systemctl start superset",
        )

        instance = ec2.Instance(
            self,
            "AnalyticsInstanceV2",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3,
                ec2.InstanceSize.MEDIUM,  # micro je premalo za Superset+Postgres na istoj masini
            ),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            security_group=ec2_sg,
            role=ec2_role,
            user_data=user_data,
        )

        # -----------------------------------------------------------------
        # Lambda - sada u VPC-u (Private Isolated subnet), pristupa
        # Postgres instanci preko privatne DNS/IP adrese, ne preko javnog
        # DNS-a kao u originalu. Connection string vise ne sadrzi
        # hardkodovanu lozinku, vec je "dynamic reference" ka Secrets
        # Manageru koji CDK resolve-uje bezbedno pri deploy-u.
        # -----------------------------------------------------------------
        _lambda.Function(
            self,
            "GoldToPostgresLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_incremental_handler.lambda_handler",
            code=_lambda.Code.from_asset(
                "lambdas/analyticsVisualization",
                bundling=BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_11.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install --no-cache-dir sqlalchemy pg8000 -t /asset-output && cp -au . /asset-output",
                    ],
                ),
            ),
            layers=[
                _lambda.LayerVersion.from_layer_version_arn(
                    self,
                    "AwsSdkPandasLayer",
                    # NAPOMENA: ovaj ARN (nalog 336392948345) je vezan za
                    # eu-central-1. Ako se stack ikad deploy-uje u drugi
                    # region, treba proveriti ispravan ARN za taj region na
                    # AWS SDK for pandas dokumentaciji.
                    f"arn:aws:lambda:{self.region}:336392948345:layer:AWSSDKPandas-Python311:21",
                ),
            ],
            timeout=Duration.minutes(10),
            memory_size=1024,
            role=lambda_role,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[lambda_sg],
            environment={
                "S3_BUCKET": data_lake.bucket_name,
                "S3_PREFIX": "gold/",
                "PG_CONN": (
                    "postgresql+pg8000://"
                    f"{db_secret.secret_value_from_json('username').unsafe_unwrap()}:"
                    f"{db_secret.secret_value_from_json('password').unsafe_unwrap()}"
                    f"@{instance.instance_private_dns_name}:5432/analytics"
                ),
            },
        )