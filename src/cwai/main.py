import typer
from typing_extensions import Annotated
from dataclasses import dataclass
import boto3
import json
from rich.console import Console

console = Console()


@dataclass
class BedrockBody:
    prompt: str
    max_tokens_to_sample: int
    temperature: float
    top_p: float
    anthropic_version: str = "bedrock-2023-05-31"

    def to_dict(self):
        return {
            "messages": [{"role": "user", "content": self.prompt}],
            "max_tokens": self.max_tokens_to_sample,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "anthropic_version": self.anthropic_version,
        }


def response_format(response_string: str) -> str:
    """format bedrock response"""
    try:
        json_response = json.loads(response_string)
    except json.JSONDecodeError as e:
        raise e

    content = json_response["content"][0].get("text", "")
    return content


def bedrock_analyze(result_string: str) -> str:
    """call bedrock for summary"""
    body = BedrockBody(
        prompt=f"Please create some insights on the following log string in plain text no markdown.{result_string}",
        max_tokens_to_sample=1000,
        temperature=0,
        top_p=1,
    )

    blob_body = bytes(json.dumps(body.to_dict()), "utf-8")

    bedrock_client = boto3.client("bedrock-runtime")

    bedrock_resp = bedrock_client.invoke_model(
        modelId="anthropic.claude-3-haiku-20240307-v1:0",
        body=blob_body,
        contentType="application/json",
    )

    response_blob = bedrock_resp["body"].read()
    response_string = response_blob.decode("utf-8")
    response_string_formatted = response_format(response_string)
    return response_string_formatted


def recent_log_stream(log_group_arn: str) -> str:
    """get most recent log stream"""
    logs_client = boto3.client("logs")

    response = logs_client.describe_log_streams(
        logGroupIdentifier=log_group_arn,
        orderBy="LastEventTime",
        descending=True,
        limit=1,
    )
    log_streams = response.get("logStreams", [])
    if log_streams:
        recent_stream_name = log_streams[0]["logStreamName"]
        return recent_stream_name
    else:
        raise Exception("No log streams found for the given log group ARN.")


def fetch_analysis(log_group_arn: str) -> str:
    # get analysis string from bedrock
    logs_client = boto3.client("logs")

    log_stream_name = recent_log_stream(log_group_arn)
    console.print(
        "[bold magenta]Identified log: {}/{}[/bold magenta]\n\n".format(
            log_group_arn, log_stream_name
        )
    )
    response = logs_client.get_log_events(
        logGroupIdentifier=log_group_arn, logStreamName=log_stream_name, limit=50
    )
    events = response.get("events", [])
    if not events:
        raise Exception("Unable to pull any events from the log.")

    result_string = "\n".join(
        [f"[{event['timestamp']}] {event['message']}" for event in events]
    )
    analysis = bedrock_analyze(result_string)
    return analysis


app = typer.Typer()


@app.command("about")
def run_main():
    print(f"insights for cloudwatch logs with gen ai")


@app.command("inspect")
def run_command(
    arn: Annotated[str, typer.Argument(help="log group arn")],
):
    analysis = fetch_analysis(arn)
    console.print(analysis)


if __name__ == "__main__":
    app()
