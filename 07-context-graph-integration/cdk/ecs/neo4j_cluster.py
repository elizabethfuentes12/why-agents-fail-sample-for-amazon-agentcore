from aws_cdk import (
    Duration,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_elasticloadbalancingv2 as elbv2,
    aws_logs as logs,
    aws_secretsmanager as secretsmanager,
    aws_iam as iam,
    aws_s3 as s3,
    aws_ecr as ecr,
    RemovalPolicy,
)
from constructs import Construct
import os


class Neo4jCluster(Construct):
    """Neo4j database cluster on ECS Fargate with Network Load Balancer.

    This construct creates:
    - VPC with public subnets (for NLB) and private subnets (for Fargate)
    - Security group allowing Bolt protocol (port 7687)
    - ECS cluster and Fargate task definition
    - Network Load Balancer for stable endpoint
    - Secrets Manager secret for Neo4j password
    - CloudWatch log group for container logs
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        cpu: int = 2048,
        memory_limit_mib: int = 4096,
        neo4j_ecr_image_uri: str = None,
        backup_ecr_image_uri: str = None,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get AWS account and region for ECR image URIs
        account = os.environ.get('CDK_DEFAULT_ACCOUNT')
        region = os.environ.get('CDK_DEFAULT_REGION', 'us-east-1')

        # Default ECR image URIs if not provided
        if not neo4j_ecr_image_uri:
            neo4j_ecr_image_uri = f"{account}.dkr.ecr.{region}.amazonaws.com/neo4j-enterprise:latest"
        if not backup_ecr_image_uri:
            backup_ecr_image_uri = f"{account}.dkr.ecr.{region}.amazonaws.com/neo4j-backup-sidecar:latest"

        # Reference ECR repositories (must exist before deploy)
        neo4j_repo = ecr.Repository.from_repository_name(
            self, "Neo4jEcrRepo", "neo4j-enterprise"
        )
        backup_repo = ecr.Repository.from_repository_name(
            self, "BackupEcrRepo", "neo4j-backup-sidecar"
        )

        # Create VPC without NAT Gateway (cost optimization)
        # Images come from ECR via VPC endpoints (no internet access needed)
        self.vpc = ec2.Vpc(
            self,
            "Neo4jVPC",
            max_azs=2,
            nat_gateways=0,  # No NAT Gateway - saves $35/month
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24
                )
            ]
        )

        # Add VPC Endpoints for private ECR and S3 access (no internet needed)
        # S3 Gateway Endpoint (free)
        self.vpc.add_gateway_endpoint(
            "S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3
        )

        # ECR API Endpoint (~$7/month)
        self.vpc.add_interface_endpoint(
            "EcrApiEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.ECR
        )

        # ECR Docker Endpoint (~$7/month)
        self.vpc.add_interface_endpoint(
            "EcrDockerEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER
        )

        # CloudWatch Logs Endpoint (for logging without internet)
        self.vpc.add_interface_endpoint(
            "CloudWatchLogsEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS
        )

        # Secrets Manager Endpoint (for password retrieval)
        self.vpc.add_interface_endpoint(
            "SecretsManagerEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER
        )

        # Create Neo4j password secret
        self.neo4j_secret = secretsmanager.Secret(
            self,
            "Neo4jPassword",
            description="Neo4j database password",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                password_length=20,
                exclude_punctuation=True,
                exclude_characters=" %+~`#$&*()|[]{}:;<>?!'/@\"\\="
            ),
            removal_policy=RemovalPolicy.DESTROY
        )

        # Create S3 bucket for Neo4j dumps (persistence across task restarts)
        self.dump_bucket = s3.Bucket(
            self,
            "DumpBucket",
            versioned=False,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,  # Auto-empty bucket on stack delete
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="cleanup-old-dumps",
                    enabled=True,
                    expiration=Duration.days(30)
                )
            ]
        )

        # Security group for Neo4j (Bolt port 7687)
        self.security_group = ec2.SecurityGroup(
            self,
            "Neo4jSecurityGroup",
            vpc=self.vpc,
            description="Neo4j Bolt protocol access (port 7687)",
            allow_all_outbound=True
        )

        # Allow Bolt access from anywhere (can be restricted to VPC CIDR if needed)
        self.security_group.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(7687),
            description="Neo4j Bolt from anywhere"
        )

        # ECS Cluster
        self.cluster = ecs.Cluster(
            self,
            "Neo4jCluster",
            vpc=self.vpc,
            container_insights=True
        )

        # Task execution role (for pulling images and accessing secrets)
        execution_role = iam.Role(
            self,
            "Neo4jTaskExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                )
            ]
        )

        # Grant secret read permission to execution role
        self.neo4j_secret.grant_read(execution_role)

        # Grant ECR read permissions to execution role
        neo4j_repo.grant_pull(execution_role)
        backup_repo.grant_pull(execution_role)

        # Task role (for application-level permissions - S3 dump access)
        task_role = iam.Role(
            self,
            "Neo4jTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com")
        )

        # Grant S3 access to task role for dump backup/restore
        self.dump_bucket.grant_read_write(task_role)

        # CloudWatch log group for Neo4j logs
        log_group = logs.LogGroup(
            self,
            "Neo4jLogGroup",
            log_group_name="/ecs/neo4j-context-graph",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY
        )

        # Task definition with ephemeral storage for dumps
        task_definition = ecs.FargateTaskDefinition(
            self,
            "Neo4jTaskDef",
            cpu=cpu,
            memory_limit_mib=memory_limit_mib,
            execution_role=execution_role,
            task_role=task_role,
            ephemeral_storage_gib=21  # Extra space for dumps
        )

        # Add shared volume for dump file
        task_definition.add_volume(name="dump-volume")

        # Sidecar container: downloads dump from S3, then exits
        dump_downloader = task_definition.add_container(
            "dump-downloader",
            image=ecs.ContainerImage.from_registry("amazon/aws-cli:latest"),
            essential=False,  # Non-essential, exits after download
            entry_point=["/bin/sh", "-c"],
            command=[
                f"echo 'Downloading dump from S3...' && "
                f"aws s3 cp s3://{self.dump_bucket.bucket_name}/neo4j-graph.dump /dump/neo4j-graph.dump 2>&1 || "
                f"(echo 'No dump found in S3, starting with empty database' && touch /dump/neo4j-graph.dump) && "
                f"echo 'Dump ready.'"
            ],
            environment={
                "DUMP_BUCKET": self.dump_bucket.bucket_name
            },
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="downloader",
                log_group=log_group
            )
        )

        # Mount volume in downloader
        dump_downloader.add_mount_points(
            ecs.MountPoint(
                source_volume="dump-volume",
                container_path="/dump",
                read_only=False
            )
        )

        # Neo4j container - waits for downloader SUCCESS, then loads dump and starts
        neo4j_container = task_definition.add_container(
            "neo4j",
            image=ecs.ContainerImage.from_ecr_repository(neo4j_repo, "latest"),
            essential=True,
            port_mappings=[
                ecs.PortMapping(
                    container_port=7687,
                    protocol=ecs.Protocol.TCP,
                    name="bolt"
                )
            ],
            environment={
                "NEO4J_ACCEPT_LICENSE_AGREEMENT": "yes",
                "NEO4J_PLUGINS": "[\"apoc\"]"  # Enable APOC for backup exports
            },
            secrets={
                "NEO4J_PASSWORD": ecs.Secret.from_secrets_manager(self.neo4j_secret)
            },
            entry_point=["/bin/bash", "-c"],
            command=[
                "set -e && "
                "echo 'Loading database from dump...' && "
                "chown -R neo4j:neo4j /var/lib/neo4j && "
                "if [ -s /dump/neo4j-graph.dump ]; then "
                "  neo4j-admin database load neo4j --from-stdin --overwrite-destination=true < /dump/neo4j-graph.dump; "
                "else "
                "  echo 'Empty dump file, starting with clean database'; "
                "fi && "
                "echo 'Configuring listeners...' && "
                "sed -i 's/^#*\\s*server\\.default_listen_address=.*/server.default_listen_address=0.0.0.0/' /var/lib/neo4j/conf/neo4j.conf && "
                "grep -q '^server.default_listen_address' /var/lib/neo4j/conf/neo4j.conf || echo 'server.default_listen_address=0.0.0.0' >> /var/lib/neo4j/conf/neo4j.conf && "
                "echo 'Setting password...' && "
                "neo4j-admin dbms set-initial-password \"$NEO4J_PASSWORD\" 2>&1 || true && "
                "echo 'Starting Neo4j...' && "
                "export NEO4J_AUTH=\"neo4j/$NEO4J_PASSWORD\" && "
                "exec neo4j console"
            ],
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="neo4j",
                log_group=log_group
            ),
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "cypher-shell -u neo4j -p \"$NEO4J_PASSWORD\" 'RETURN 1' || exit 1"],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(10),
                retries=3,
                start_period=Duration.seconds(120)  # 2 minutes to load dump and start
            )
        )

        # Mount volume in Neo4j (read dump)
        neo4j_container.add_mount_points(
            ecs.MountPoint(
                source_volume="dump-volume",
                container_path="/dump",
                read_only=True
            )
        )

        # Neo4j depends on downloader SUCCESS
        neo4j_container.add_container_dependencies(
            ecs.ContainerDependency(
                container=dump_downloader,
                condition=ecs.ContainerDependencyCondition.SUCCESS
            )
        )

        # Backup sidecar: hourly dumps to S3 + final dump on SIGTERM
        # Uses custom image with AWS CLI pre-installed (no internet needed)
        backup_sidecar = task_definition.add_container(
            "backup-sidecar",
            image=ecs.ContainerImage.from_ecr_repository(backup_repo, "latest"),
            essential=False,  # Non-essential, Neo4j can run without it
            entry_point=["/bin/bash", "-c"],
            command=[
                "RUNNING=true && "
                "trap 'echo Received SIGTERM; RUNNING=false' SIGTERM SIGINT && "
                "echo Waiting for Neo4j... && "
                "for i in {1..60}; do "
                "  if cypher-shell -a bolt://localhost:7687 -u neo4j -p \"$NEO4J_PASSWORD\" 'RETURN 1' &>/dev/null; then "
                "    echo Neo4j is ready; "
                "    break; "
                "  fi; "
                "  sleep 5; "
                "done && "
                "BACKUP_INTERVAL=900 && "
                "ELAPSED=0 && "
                "echo Backup sidecar started, interval: ${BACKUP_INTERVAL}s && "
                "while $RUNNING; do "
                "  if [ $ELAPSED -ge $BACKUP_INTERVAL ]; then "
                "    TIMESTAMP=$(date +%Y%m%d-%H%M%S) && "
                "    echo Starting backup... && "
                "    cypher-shell -a bolt://localhost:7687 -u neo4j -p \"$NEO4J_PASSWORD\" "
                "      \"CALL apoc.export.cypher.all('/tmp/neo4j-${TIMESTAMP}.cypher', {format: 'cypher-shell'}) "
                "       YIELD file, nodes, relationships, properties, time "
                "       RETURN file, nodes, relationships, properties, time\" 2>&1 | tee /tmp/export.log && "
                "    if [ -f /tmp/neo4j-${TIMESTAMP}.cypher ]; then "
                "      aws s3 cp /tmp/neo4j-${TIMESTAMP}.cypher s3://${S3_BUCKET}/neo4j-graph.cypher --region ${AWS_REGION} && "
                "      aws s3 cp /tmp/neo4j-${TIMESTAMP}.cypher s3://${S3_BUCKET}/backups/neo4j-${TIMESTAMP}.cypher --region ${AWS_REGION} && "
                "      echo Backup complete: neo4j-${TIMESTAMP}.cypher && "
                "      rm -f /tmp/neo4j-${TIMESTAMP}.cypher; "
                "    else "
                "      echo ERROR: Backup file not created; "
                "      cat /tmp/export.log; "
                "    fi && "
                "    ELAPSED=0; "
                "  fi; "
                "  sleep 10 && "
                "  ELAPSED=$((ELAPSED + 10)); "
                "done && "
                "echo Creating final dump... && "
                "TIMESTAMP=$(date +%Y%m%d-%H%M%S) && "
                "cypher-shell -a bolt://localhost:7687 -u neo4j -p \"$NEO4J_PASSWORD\" "
                "  \"CALL apoc.export.cypher.all('/tmp/neo4j-final-${TIMESTAMP}.cypher', {format: 'cypher-shell'}) "
                "   YIELD file RETURN file\" &>/dev/null && "
                "aws s3 cp /tmp/neo4j-final-${TIMESTAMP}.cypher s3://${S3_BUCKET}/neo4j-graph.cypher --region ${AWS_REGION} && "
                "echo Final backup complete"
            ],
            environment={
                "S3_BUCKET": self.dump_bucket.bucket_name,
                "AWS_REGION": os.environ.get("CDK_DEFAULT_REGION", os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1")))
            },
            secrets={
                "NEO4J_PASSWORD": ecs.Secret.from_secrets_manager(self.neo4j_secret)
            },
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="backup",
                log_group=log_group
            )
        )

        # Backup sidecar depends on Neo4j being healthy
        backup_sidecar.add_container_dependencies(
            ecs.ContainerDependency(
                container=neo4j_container,
                condition=ecs.ContainerDependencyCondition.HEALTHY
            )
        )

        # Internal Network Load Balancer (VPC-only access, more secure)
        self.nlb = elbv2.NetworkLoadBalancer(
            self,
            "Neo4jNLB",
            vpc=self.vpc,
            internet_facing=False,  # Internal only - accessed from VPC
            cross_zone_enabled=True
        )

        # Target group for Neo4j Bolt
        target_group = elbv2.NetworkTargetGroup(
            self,
            "Neo4jTargetGroup",
            vpc=self.vpc,
            port=7687,
            protocol=elbv2.Protocol.TCP,
            target_type=elbv2.TargetType.IP,
            health_check=elbv2.HealthCheck(
                enabled=True,
                protocol=elbv2.Protocol.TCP,
                interval=Duration.seconds(30),
                healthy_threshold_count=2,
                unhealthy_threshold_count=2
            ),
            deregistration_delay=Duration.seconds(30)
        )

        # Add listener to NLB
        self.nlb.add_listener(
            "BoltListener",
            port=7687,
            protocol=elbv2.Protocol.TCP,
            default_target_groups=[target_group]
        )

        # Fargate Spot service (70% cost savings vs standard Fargate)
        # Trade-off: AWS can interrupt with 2-minute warning, but backups every 15min mitigate data loss
        self.service = ecs.FargateService(
            self,
            "Neo4jService",
            cluster=self.cluster,
            task_definition=task_definition,
            desired_count=1,
            capacity_provider_strategies=[
                ecs.CapacityProviderStrategy(
                    capacity_provider="FARGATE_SPOT",
                    weight=1,
                    base=0
                )
            ],
            security_groups=[self.security_group],
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            assign_public_ip=False,
            # 5 minutes grace period for:
            # 1. Download dump from S3 (~30s)
            # 2. Load dump into Neo4j (~1-2min depending on size)
            # 3. Start Neo4j and pass health check (~1-2min)
            health_check_grace_period=Duration.seconds(300),
            # Circuit breaker disabled (like workshop pattern) but with deployment configuration
            circuit_breaker=ecs.DeploymentCircuitBreaker(
                enable=False,
                rollback=False
            ),
            deployment_controller=ecs.DeploymentController(
                type=ecs.DeploymentControllerType.ECS
            ),
            min_healthy_percent=0,  # Allow full replacement during updates
            max_healthy_percent=100,  # No extra tasks during updates
            # Enable ECS Exec for debugging
            enable_execute_command=True
        )

        # Attach service to target group
        self.service.attach_to_network_target_group(target_group)

        # Expose Neo4j URI as property
        self.neo4j_uri = f"bolt://{self.nlb.load_balancer_dns_name}:7687"
