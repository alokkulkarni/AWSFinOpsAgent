"""Map our service codes to draw.io AWS4 resource-icon glyphs + colors."""
from __future__ import annotations

# service code -> mxgraph.aws4 resIcon name
SERVICE_RESICON = {
    "ec2": "ec2", "lambda": "lambda", "s3": "s3",
    "ecs": "elastic_container_service", "eks": "elastic_kubernetes_service",
    "rds": "rds", "dynamodb": "dynamodb", "elasticache": "elasticache",
    "memorydb": "memorydb_for_redis", "cloudfront": "cloudfront",
    "iam": "identity_and_access_management", "kms": "key_management_service",
    "secretsmanager": "secrets_manager", "logs": "cloudwatch", "cloudwatch": "cloudwatch",
    "cloudtrail": "cloudtrail", "cloudformation": "cloudformation",
    "sns": "simple_notification_service", "sqs": "simple_queue_service",
    "apigateway": "api_gateway", "execute-api": "api_gateway",
    "elasticloadbalancing": "elastic_load_balancing", "elb": "elastic_load_balancing",
    "route53": "route_53", "bedrock": "bedrock", "states": "step_functions",
    "glue": "glue", "athena": "athena", "lex": "lex", "amplify": "amplify",
    "wisdom": "wisdom", "connect": "connect", "sagemaker": "sagemaker",
    "ssm": "systems_manager", "efs": "elastic_file_system", "ecr": "elastic_container_registry",
}

# AWS category fill colors
_CATEGORY_COLOR = {
    "compute": "#ED7100", "storage": "#7AA116", "database": "#C925D1",
    "network": "#8C4FFF", "security": "#DD344C", "mgmt": "#E7157B", "general": "#232F3E",
}
_SERVICE_CATEGORY = {
    "ec2": "compute", "lambda": "compute", "ecs": "compute", "eks": "compute",
    "s3": "storage", "efs": "storage", "ecr": "storage",
    "rds": "database", "dynamodb": "database", "memorydb": "database", "elasticache": "database",
    "cloudfront": "network", "route53": "network", "elasticloadbalancing": "network",
    "apigateway": "network", "elb": "network",
    "iam": "security", "kms": "security", "secretsmanager": "security",
    "cloudwatch": "mgmt", "logs": "mgmt", "cloudtrail": "mgmt", "cloudformation": "mgmt",
}


def res_icon(service: str) -> str:
    return SERVICE_RESICON.get(service, "general")


def fill_color(service: str) -> str:
    return _CATEGORY_COLOR.get(_SERVICE_CATEGORY.get(service, "general"), "#ED7100")


def icon_style(service: str) -> str:
    return (
        "sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;"
        f"fillColor={fill_color(service)};strokeColor=none;dashed=0;"
        "verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;"
        f"aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.{res_icon(service)};"
    )
