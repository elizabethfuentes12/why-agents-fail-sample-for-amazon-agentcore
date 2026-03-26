"""Shared configuration for local and production environments.

Table names and region are resolved from environment variables.
In production, CDK injects these into the AgentCore Runtime.
Locally, they default to the same names CDK creates.
"""

import os

import boto3

STACK_NAME = "HotelBookingAgentStack"

HOTELS_TABLE = os.environ.get("HOTELS_TABLE", f"{STACK_NAME}-Hotels")
BOOKINGS_TABLE = os.environ.get("BOOKINGS_TABLE", f"{STACK_NAME}-Bookings")
STEERING_RULES_TABLE = os.environ.get("STEERING_RULES_TABLE", f"{STACK_NAME}-SteeringRules")


def get_dynamodb_resource():
    """Get DynamoDB resource using default credential chain."""
    session = boto3.Session()
    return session.resource("dynamodb")
