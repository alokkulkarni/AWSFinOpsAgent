"""On-demand deep describe — the thin inventory (id/type/region/tags) is great for breadth; this
fetches the live, service-specific object for ONE resource so the agent answers attachment / orphan
/ config questions definitively instead of hedging.

Coverage, in priority order:
  1. special handlers for awkward APIs (S3 multi-call, SQS url, ECS service/task need a cluster),
  2. a broad declarative describe table (EC2 family + ELB/Lambda/RDS/DynamoDB/SNS/ECS/EKS/IAM/
     CloudFront/Route53/KMS/SecretsManager/StepFunctions/ElastiCache/ECR/EFS/Kinesis/CloudWatch/
     Logs/SSM/CloudFormation/AutoScaling/Cognito/ACM/EventBridge/CloudTrail/…),
  3. an AWS Config universal fallback (any type Config records, when recording is enabled),
  4. a graceful note (inventory + tags still shown) for anything else.

Resource-type keys vary by source (ARN-parsed vs Resource Explorer native, e.g.
`elasticloadbalancing:listener/app`), so lookups normalize to `service:firstsubtype` and fall back
to service. JSON-safe (datetimes → ISO).
"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

from finops_core.aws.session import client


def _d(svc, method, arg, extract, as_list=True, src="id", region=None):
    return dict(svc=svc, method=method, arg=arg, extract=extract, as_list=as_list,
                src=src, region=region)


# Declarative describes, keyed on normalized `service:subtype` (or bare service).
_DETAIL = {
    # --- EC2 networking / compute family ---
    "ec2:network-interface": _d("ec2", "describe_network_interfaces", "NetworkInterfaceIds", ("list", "NetworkInterfaces")),
    "ec2:instance": _d("ec2", "describe_instances", "InstanceIds", ("list", "Reservations", "Instances")),
    "ec2:security-group": _d("ec2", "describe_security_groups", "GroupIds", ("list", "SecurityGroups")),
    "ec2:subnet": _d("ec2", "describe_subnets", "SubnetIds", ("list", "Subnets")),
    "ec2:vpc": _d("ec2", "describe_vpcs", "VpcIds", ("list", "Vpcs")),
    "ec2:natgateway": _d("ec2", "describe_nat_gateways", "NatGatewayIds", ("list", "NatGateways")),
    "ec2:internet-gateway": _d("ec2", "describe_internet_gateways", "InternetGatewayIds", ("list", "InternetGateways")),
    "ec2:route-table": _d("ec2", "describe_route_tables", "RouteTableIds", ("list", "RouteTables")),
    "ec2:vpc-endpoint": _d("ec2", "describe_vpc_endpoints", "VpcEndpointIds", ("list", "VpcEndpoints")),
    "ec2:vpc-peering-connection": _d("ec2", "describe_vpc_peering_connections", "VpcPeeringConnectionIds", ("list", "VpcPeeringConnections")),
    "ec2:network-acl": _d("ec2", "describe_network_acls", "NetworkAclIds", ("list", "NetworkAcls")),
    "ec2:volume": _d("ec2", "describe_volumes", "VolumeIds", ("list", "Volumes")),
    "ec2:snapshot": _d("ec2", "describe_snapshots", "SnapshotIds", ("list", "Snapshots")),
    "ec2:transit-gateway": _d("ec2", "describe_transit_gateways", "TransitGatewayIds", ("list", "TransitGateways")),
    "ec2:dhcp-options": _d("ec2", "describe_dhcp_options", "DhcpOptionsIds", ("list", "DhcpOptions")),
    "ec2:launch-template": _d("ec2", "describe_launch_templates", "LaunchTemplateIds", ("list", "LaunchTemplates")),
    "ec2:elastic-ip": _d("ec2", "describe_addresses", "AllocationIds", ("list", "Addresses")),
    "ec2:image": _d("ec2", "describe_images", "ImageIds", ("list", "Images")),
    "ec2:vpn-gateway": _d("ec2", "describe_vpn_gateways", "VpnGatewayIds", ("list", "VpnGateways")),
    "ec2:vpn-connection": _d("ec2", "describe_vpn_connections", "VpnConnectionIds", ("list", "VpnConnections")),
    "ec2:customer-gateway": _d("ec2", "describe_customer_gateways", "CustomerGatewayIds", ("list", "CustomerGateways")),
    "ec2:flow-log": _d("ec2", "describe_flow_logs", "FlowLogIds", ("list", "FlowLogs")),
    # --- Elastic Load Balancing v2 (ARN-keyed) ---
    "elasticloadbalancing:loadbalancer": _d("elbv2", "describe_load_balancers", "LoadBalancerArns", ("list", "LoadBalancers"), src="arn"),
    "elasticloadbalancing:targetgroup": _d("elbv2", "describe_target_groups", "TargetGroupArns", ("list", "TargetGroups"), src="arn"),
    "elasticloadbalancing:listener": _d("elbv2", "describe_listeners", "ListenerArns", ("list", "Listeners"), src="arn"),
    # --- Serverless / containers ---
    "lambda:function": _d("lambda", "get_function_configuration", "FunctionName", ("self",), as_list=False),
    "ecs:cluster": _d("ecs", "describe_clusters", "clusters", ("list", "clusters")),
    "ecs:task-definition": _d("ecs", "describe_task_definition", "taskDefinition", ("wrap", "taskDefinition"), as_list=False),
    "eks:cluster": _d("eks", "describe_cluster", "name", ("wrap", "cluster"), as_list=False),
    "ecr:repository": _d("ecr", "describe_repositories", "repositoryNames", ("list", "repositories")),
    "apprunner:service": _d("apprunner", "describe_service", "ServiceArn", ("wrap", "Service"), as_list=False, src="arn"),
    # --- Databases / cache / streaming ---
    "rds:db": _d("rds", "describe_db_instances", "DBInstanceIdentifier", ("list", "DBInstances"), as_list=False),
    "rds:cluster": _d("rds", "describe_db_clusters", "DBClusterIdentifier", ("list", "DBClusters"), as_list=False),
    "dynamodb:table": _d("dynamodb", "describe_table", "TableName", ("wrap", "Table"), as_list=False),
    "elasticache:cluster": _d("elasticache", "describe_cache_clusters", "CacheClusterId", ("list", "CacheClusters"), as_list=False),
    "kinesis:stream": _d("kinesis", "describe_stream_summary", "StreamName", ("wrap", "StreamDescriptionSummary"), as_list=False),
    "elasticfilesystem:file-system": _d("efs", "describe_file_systems", "FileSystemId", ("list", "FileSystems"), as_list=False),
    # --- Messaging / events / workflow ---
    "sns": _d("sns", "get_topic_attributes", "TopicArn", ("wrap", "Attributes"), as_list=False, src="arn"),
    "states:stateMachine": _d("stepfunctions", "describe_state_machine", "stateMachineArn", ("self",), as_list=False, src="arn"),
    "events:rule": _d("events", "describe_rule", "Name", ("self",), as_list=False),
    # --- Security / identity / secrets ---
    "iam:role": _d("iam", "get_role", "RoleName", ("wrap", "Role"), as_list=False),
    "iam:user": _d("iam", "get_user", "UserName", ("wrap", "User"), as_list=False),
    "iam:group": _d("iam", "get_group", "GroupName", ("wrap", "Group"), as_list=False),
    "iam:policy": _d("iam", "get_policy", "PolicyArn", ("wrap", "Policy"), as_list=False, src="arn"),
    "iam:instance-profile": _d("iam", "get_instance_profile", "InstanceProfileName", ("wrap", "InstanceProfile"), as_list=False),
    "kms:key": _d("kms", "describe_key", "KeyId", ("wrap", "KeyMetadata"), as_list=False),
    "secretsmanager:secret": _d("secretsmanager", "describe_secret", "SecretId", ("self",), as_list=False, src="arn"),
    "acm:certificate": _d("acm", "describe_certificate", "CertificateArn", ("wrap", "Certificate"), as_list=False, src="arn"),
    "cognito-idp:userpool": _d("cognito-idp", "describe_user_pool", "UserPoolId", ("wrap", "UserPool"), as_list=False),
    # --- Edge / DNS / CDN (global → us-east-1) ---
    "cloudfront:distribution": _d("cloudfront", "get_distribution", "Id", ("wrap", "Distribution"), as_list=False, region="us-east-1"),
    "route53:hostedzone": _d("route53", "get_hosted_zone", "Id", ("wrap", "HostedZone"), as_list=False, region="us-east-1"),
    # --- More managed services (long tail present in real estates) ---
    "rds:og": _d("rds", "describe_option_groups", "OptionGroupName", ("list", "OptionGroupsList"), as_list=False),
    "rds:pg": _d("rds", "describe_db_parameter_groups", "DBParameterGroupName", ("list", "DBParameterGroups"), as_list=False),
    "rds:subgrp": _d("rds", "describe_db_subnet_groups", "DBSubnetGroupName", ("list", "DBSubnetGroups"), as_list=False),
    "mq:broker": _d("mq", "describe_broker", "BrokerId", ("self",), as_list=False),
    "ses:identity": _d("sesv2", "get_email_identity", "EmailIdentity", ("self",), as_list=False),
    "ses:configuration-set": _d("sesv2", "get_configuration_set", "ConfigurationSetName", ("self",), as_list=False),
    "sagemaker:domain": _d("sagemaker", "describe_domain", "DomainId", ("self",), as_list=False),
    "memorydb:acl": _d("memorydb", "describe_acls", "ACLName", ("list", "ACLs"), as_list=False),
    "apprunner:autoscalingconfiguration": _d("apprunner", "describe_auto_scaling_configuration", "AutoScalingConfigurationArn", ("wrap", "AutoScalingConfiguration"), as_list=False, src="arn"),
    "amplify:apps": _d("amplify", "get_app", "appId", ("wrap", "app"), as_list=False),
    "athena:workgroup": _d("athena", "get_work_group", "WorkGroup", ("wrap", "WorkGroup"), as_list=False),
    "athena:datacatalog": _d("athena", "get_data_catalog", "Name", ("wrap", "DataCatalog"), as_list=False),
    "backup:backup-vault": _d("backup", "describe_backup_vault", "BackupVaultName", ("self",), as_list=False),
    "backup:backup-plan": _d("backup", "get_backup_plan", "BackupPlanId", ("self",), as_list=False),
    "appsync:apis": _d("appsync", "get_graphql_api", "apiId", ("wrap", "graphqlApi"), as_list=False),
    "cognito-identity:identitypool": _d("cognito-identity", "describe_identity_pool", "IdentityPoolId", ("self",), as_list=False),
    "bedrock:guardrail": _d("bedrock", "get_guardrail", "guardrailIdentifier", ("self",), as_list=False),
    "bedrock:knowledge-base": _d("bedrock-agent", "get_knowledge_base", "knowledgeBaseId", ("wrap", "knowledgeBase"), as_list=False),
    "bedrock:agent": _d("bedrock-agent", "get_agent", "agentId", ("wrap", "agent"), as_list=False),
    "connect:instance": _d("connect", "describe_instance", "InstanceId", ("wrap", "Instance"), as_list=False),
    "appconfig:application": _d("appconfig", "get_application", "ApplicationId", ("self",), as_list=False),
    "ec2:security-group-rule": _d("ec2", "describe_security_group_rules", "SecurityGroupRuleIds", ("list", "SecurityGroupRules")),
    "cloudfront:function": _d("cloudfront", "describe_function", "Name", ("wrap", "FunctionSummary"), as_list=False, region="us-east-1"),
    # --- Ops / config / observability ---
    "cloudformation:stack": _d("cloudformation", "describe_stacks", "StackName", ("list", "Stacks"), as_list=False),
    "autoscaling:autoScalingGroup": _d("autoscaling", "describe_auto_scaling_groups", "AutoScalingGroupNames", ("list", "AutoScalingGroups")),
    "cloudwatch:alarm": _d("cloudwatch", "describe_alarms", "AlarmNames", ("list", "MetricAlarms")),
    "logs:log-group": _d("logs", "describe_log_groups", "logGroupNamePrefix", ("list", "logGroups"), as_list=False),
    "cloudtrail:trail": _d("cloudtrail", "get_trail", "Name", ("wrap", "Trail"), as_list=False, src="arn"),
}

# AWS Config type names for the universal fallback (works only where Config recording is on).
_CONFIG_TYPE = {
    "ec2:instance": "AWS::EC2::Instance", "ec2:vpc": "AWS::EC2::VPC", "ec2:subnet": "AWS::EC2::Subnet",
    "ec2:security-group": "AWS::EC2::SecurityGroup", "ec2:network-interface": "AWS::EC2::NetworkInterface",
    "ec2:volume": "AWS::EC2::Volume", "ec2:natgateway": "AWS::EC2::NatGateway",
    "ec2:internet-gateway": "AWS::EC2::InternetGateway", "ec2:route-table": "AWS::EC2::RouteTable",
    "lambda:function": "AWS::Lambda::Function", "s3": "AWS::S3::Bucket", "rds:db": "AWS::RDS::DBInstance",
    "rds:cluster": "AWS::RDS::DBCluster", "dynamodb:table": "AWS::DynamoDB::Table",
    "elasticloadbalancing:loadbalancer": "AWS::ElasticLoadBalancingV2::LoadBalancer",
    "cloudfront:distribution": "AWS::CloudFront::Distribution", "iam:role": "AWS::IAM::Role",
    "iam:user": "AWS::IAM::User", "iam:policy": "AWS::IAM::Policy", "iam:group": "AWS::IAM::Group",
    "sns": "AWS::SNS::Topic", "sqs": "AWS::SQS::Queue", "kms:key": "AWS::KMS::Key",
    "secretsmanager:secret": "AWS::SecretsManager::Secret", "cloudtrail:trail": "AWS::CloudTrail::Trail",
    "cloudformation:stack": "AWS::CloudFormation::Stack", "ecs:cluster": "AWS::ECS::Cluster",
    "ecs:service": "AWS::ECS::Service", "eks:cluster": "AWS::EKS::Cluster",
    "cognito-idp:userpool": "AWS::Cognito::UserPool", "apigateway:restapis": "AWS::ApiGateway::RestApi",
    "elasticfilesystem:file-system": "AWS::EFS::FileSystem", "elasticache:cluster": "AWS::ElastiCache::CacheCluster",
}


def _norm(resource_type: str) -> str:
    """`service:firstsubtype` — strips RE's extra `/sub` and `:sub` qualifiers so e.g.
    'elasticloadbalancing:listener/app' and 'secretsmanager:secret:aria' map to their base type."""
    svc, _, rest = resource_type.partition(":")
    sub = rest.split("/", 1)[0].split(":", 1)[0]
    return f"{svc}:{sub}" if sub else svc


def _lookup(resource_type: str):
    rt = resource_type
    return (_DETAIL.get(rt) or _DETAIL.get(_norm(rt))
            or _DETAIL.get(rt.split(":", 1)[0]))


def detail_supported(resource_type: str) -> bool:
    return _lookup(resource_type) is not None or _special_for(resource_type) is not None


def _jsonsafe(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", "replace")
    if isinstance(obj, dict):
        return {k: _jsonsafe(v) for k, v in obj.items() if k != "ResponseMetadata"}
    if isinstance(obj, (list, tuple, set)):
        return [_jsonsafe(v) for v in obj]
    return obj


def _extract(resp: dict, ex: tuple):
    if ex[0] == "list":
        items = resp.get(ex[1], [])
        if len(ex) > 2:  # unwrap one level (e.g. Reservations[].Instances[])
            items = [x for grp in items for x in grp.get(ex[2], [])]
        return items[0] if items else None
    if ex[0] == "wrap":
        return resp.get(ex[1])
    if ex[0] == "self":
        return {k: v for k, v in resp.items() if k != "ResponseMetadata"}
    return None


def _describe(session, resource, spec) -> dict:
    ident = resource.arn if spec.get("src") == "arn" else resource.id
    if not ident:
        return {"detail": None, "note": "resource has no id/arn to describe"}
    try:
        api = client(session, spec["svc"], spec.get("region") or resource.region)
        arg = [ident] if spec.get("as_list") else ident
        resp = getattr(api, spec["method"])(**{spec["arg"]: arg})
        detail = _extract(resp, spec["extract"])
        if detail is None:
            return {"detail": None, "note": f"{resource.id} not found via {spec['method']}"}
        return {"detail": _jsonsafe(detail)}
    except Exception as e:
        return {"detail": None, "note": f"{spec['method']}: {type(e).__name__}"}


# ---- special handlers (APIs that need extra context) ----

def _s3_detail(session, r) -> dict:
    s3 = client(session, "s3", "us-east-1")
    b = r.id

    def t(fn):
        try:
            return fn()
        except Exception:
            return None
    return {"detail": _jsonsafe({
        "Name": b,
        "Location": t(lambda: s3.get_bucket_location(Bucket=b).get("LocationConstraint")) or "us-east-1",
        "Versioning": t(lambda: s3.get_bucket_versioning(Bucket=b).get("Status")) or "Disabled",
        "Encryption": t(lambda: s3.get_bucket_encryption(Bucket=b).get("ServerSideEncryptionConfiguration")),
        "PublicAccessBlock": t(lambda: s3.get_public_access_block(Bucket=b).get("PublicAccessBlockConfiguration")),
        "HasPolicy": bool(t(lambda: s3.get_bucket_policy(Bucket=b).get("Policy"))),
        "Logging": t(lambda: s3.get_bucket_logging(Bucket=b).get("LoggingEnabled")),
        "Lifecycle": t(lambda: s3.get_bucket_lifecycle_configuration(Bucket=b).get("Rules")),
        "Tagging": t(lambda: s3.get_bucket_tagging(Bucket=b).get("TagSet")),
    })}


def _sqs_detail(session, r) -> dict:
    try:
        sqs = client(session, "sqs", r.region)
        url = sqs.get_queue_url(QueueName=r.id)["QueueUrl"]
        attrs = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["All"]).get("Attributes", {})
        return {"detail": _jsonsafe({"QueueUrl": url, **attrs})}
    except Exception as e:
        return {"detail": None, "note": f"sqs: {type(e).__name__}"}


def _ecs_service_detail(session, r) -> dict:
    parts = [p for p in r.id.split("/") if p]
    if len(parts) < 2:
        return {"detail": None, "note": "ecs service id lacks cluster context (need cluster/service)"}
    cluster, svc = parts[0], parts[-1]
    try:
        items = client(session, "ecs", r.region).describe_services(
            cluster=cluster, services=[svc]).get("services", [])
        return {"detail": _jsonsafe(items[0]) if items else None,
                **({} if items else {"note": f"ecs service {svc} not found in {cluster}"})}
    except Exception as e:
        return {"detail": None, "note": f"ecs: {type(e).__name__}"}


def _ssm_param_detail(session, r) -> dict:
    # the inventory id can lose the leading "/" of a parameter name — try both forms.
    try:
        ssm = client(session, "ssm", r.region)
        for name in (r.id, "/" + r.id.lstrip("/")):
            try:
                p = ssm.get_parameter(Name=name).get("Parameter")
                if p:
                    return {"detail": _jsonsafe(p)}
            except Exception:
                continue
        return {"detail": None, "note": f"ssm parameter {r.id!r} not found"}
    except Exception as e:
        return {"detail": None, "note": f"ssm: {type(e).__name__}"}


# Keyed on exact / normalized type (NOT bare-service fallback) so s3:storage-lens, s3:access-point,
# etc. don't get mis-routed to bucket logic. Both the RE form (s3:bucket) and the tagging form (s3).
_SPECIAL = {
    "s3:bucket": _s3_detail, "s3": _s3_detail,
    "sqs:queue": _sqs_detail, "sqs": _sqs_detail,
    "ecs:service": _ecs_service_detail,
    "ssm:parameter": _ssm_param_detail,
}


def _special_for(resource_type: str):
    return _SPECIAL.get(resource_type) or _SPECIAL.get(_norm(resource_type))


def _config_detail(session, resource):
    """Universal fallback via AWS Config (covers any recorded type when recording is enabled)."""
    ct = _CONFIG_TYPE.get(resource.resource_type) or _CONFIG_TYPE.get(_norm(resource.resource_type))
    if not ct:
        return None
    try:
        resp = client(session, "config", resource.region).batch_get_resource_config(
            resourceKeys=[{"resourceType": ct, "resourceId": resource.id}])
        items = resp.get("baseConfigurationItems", [])
        if not items:
            return {"detail": None,
                    "note": f"AWS Config has no recorded configuration for {resource.id} ({ct}); "
                            "enable Config recording for universal deep detail on this type."}
        conf = items[0].get("configuration")
        detail = json.loads(conf) if isinstance(conf, str) else conf
        return {"detail": _jsonsafe(detail), "source": "aws-config"}
    except Exception:
        return None


def resource_details(session, resource) -> dict:
    """Live attributes for one resource: {"detail": {...}} or {"detail": None, "note": ...}.
    Read-only and graceful."""
    rt = resource.resource_type
    special = _special_for(rt)
    if special:
        return special(session, resource)

    spec = _lookup(rt)
    if spec:
        return _describe(session, resource, spec)

    via_config = _config_detail(session, resource)
    if via_config is not None:
        return via_config

    return {"detail": None,
            "note": f"deep describe not mapped for {rt}; the inventory fields + tags above are the "
                    "available detail. (No universal AWS describe API; this type can be added on "
                    "request or surfaced via AWS Config when recording is enabled.)"}
