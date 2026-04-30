import argparse
import json
import os
import boto3
from botocore.loaders import Loader

parser = argparse.ArgumentParser()
parser.add_argument("--raw-events", action="store_true",
                    help="Print raw streaming events instead of formatted text")
args = parser.parse_args()

# --- Configuration ---
HARNESS_ARN = "arn:aws:bedrock-agentcore:us-west-2:409645756810:harness/MyBugBashHarnessEliaws-5w1B83sr2S"
REGION = "us-west-2"
ENDPOINT_URL = "https://beta.us-west-2.elcapdp.genesis-primitives.aws.dev"
SESSION_ID = "AB554EFE-AB17-40D8-B5B3-EC3AC6022CB8"

# Register the local data plane model with Boto3 (only needed for private beta)
model_dir = os.path.join(os.path.dirname(__file__), "models")
loader = Loader()
loader.search_paths.insert(0, model_dir)
session = boto3.Session(region_name=REGION)
session._session.register_component("data_loader", loader)
    
client = session.client(
    "bedrock-agentcore",
    endpoint_url=ENDPOINT_URL,
)

# Invoke Harness
response = client.invoke_harness(
    harnessArn=HARNESS_ARN,
    runtimeSessionId=SESSION_ID,
    tools=[
        {
            "type": "remote_mcp",
            "name": "exa",
            "config": {"remoteMcp": {"url": "https://mcp.exa.ai/mcp"}}
        }
    ],
    messages=[
        {
            "role": "user",
            "content": [
                {"text": "What are three fun things to do in Seattle on a rainy day? Save your answer to a Markdown file."}
            ],
        }
    ],
    # Default model if omitted
    model={
        "bedrockModelConfig": {
            "modelId": "us.anthropic.claude-haiku-4-5-20251001-v1:0"
        }
    }
)

# Stream the response in realtime
for event in response["stream"]:
    if args.raw_events:
        print(json.dumps(event, default=str))
    else:
        # Note that not all content block types are emitted here
        if "contentBlockStart" in event:
            start = event["contentBlockStart"].get("start", {})
            if "toolUse" in start:
                tool = start["toolUse"]
                print(f"\n🔧 Tool call: {tool.get('name', 'unknown')}", flush=True)
        elif "contentBlockDelta" in event:
            delta = event["contentBlockDelta"].get("delta", {})
            if "text" in delta:
                print(delta["text"], end="", flush=True)
        elif "messageStop" in event:
            print()
        elif "internalServerException" in event:
            print(f"\nError: {event['internalServerException']}")