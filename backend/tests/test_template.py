"""Static checks on backend/template.yaml (no AWS, no sam CLI)."""

from pathlib import Path

import pytest
import yaml

TEMPLATE = Path(__file__).resolve().parents[1] / "template.yaml"
SAMCONFIG = Path(__file__).resolve().parents[1] / "samconfig.toml"


class CfnLoader(yaml.SafeLoader):
    """SafeLoader that turns CloudFormation short tags (!Ref, !GetAtt, !Sub, ...) into dicts."""


def _cfn(loader, tag_suffix, node):
    name = "Ref" if tag_suffix == "Ref" else f"Fn::{tag_suffix}"
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
        if tag_suffix == "GetAtt":
            value = value.split(".")
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    else:
        value = loader.construct_mapping(node, deep=True)
    return {name: value}


CfnLoader.add_multi_constructor("!", _cfn)


@pytest.fixture(scope="module")
def tpl():
    return yaml.load(TEMPLATE.read_text(), Loader=CfnLoader)


def res(tpl, name):
    return tpl["Resources"][name]


def fn_props(tpl):
    """ApiFunction properties merged over Globals.Function."""
    merged = dict(tpl.get("Globals", {}).get("Function", {}))
    props = res(tpl, "ApiFunction")["Properties"]
    env = {**merged.get("Environment", {}).get("Variables", {}),
           **props.get("Environment", {}).get("Variables", {})}
    merged.update(props)
    merged["Environment"] = {"Variables": env}
    return merged


def test_is_sam(tpl):
    assert tpl["Transform"] == "AWS::Serverless-2016-10-31"


def test_api_function(tpl):
    assert res(tpl, "ApiFunction")["Type"] == "AWS::Serverless::Function"
    p = fn_props(tpl)
    assert p["Runtime"] == "python3.11"
    assert p["Architectures"] == ["arm64"]
    assert p["Handler"] == "agentwatch_api.handlers.api.lambda_handler"
    assert p["CodeUri"] == "src/"
    env = p["Environment"]["Variables"]
    assert env["TABLE_NAME"] == {"Ref": "EventTable"}
    assert env["TOPIC_ARN"] == {"Ref": "AlertTopic"}
    assert p["LoggingConfig"] == {"LogFormat": "JSON", "ApplicationLogLevel": "INFO"}


def test_routes(tpl):
    events = res(tpl, "ApiFunction")["Properties"]["Events"]
    routes = {(e["Properties"]["Method"].upper(), e["Properties"]["Path"])
              for e in events.values() if e["Type"] == "HttpApi"}
    assert {("POST", "/events"), ("GET", "/agents"), ("GET", "/agents/{agentId}/events"),
            ("GET", "/agents/{agentId}/config"), ("PUT", "/agents/{agentId}/config"),
            ("GET", "/agents/{agentId}/spend")} <= routes


def test_event_table(tpl):
    t = res(tpl, "EventTable")
    assert t["Type"] == "AWS::DynamoDB::Table"
    p = t["Properties"]
    assert p["BillingMode"] == "PAY_PER_REQUEST"
    assert {(k["AttributeName"], k["KeyType"]) for k in p["KeySchema"]} == {("agentId", "HASH"), ("sk", "RANGE")}
    attrs = {a["AttributeName"]: a["AttributeType"] for a in p["AttributeDefinitions"]}
    assert attrs == {"agentId": "S", "sk": "S", "gsiOwnerId": "S"}
    (gsi,) = p["GlobalSecondaryIndexes"]
    assert gsi["IndexName"] == "ownerIndex"
    assert gsi["KeySchema"] == [{"AttributeName": "gsiOwnerId", "KeyType": "HASH"}]
    assert gsi["Projection"] == {"ProjectionType": "ALL"}


def test_alert_topic_email_subscription(tpl):
    assert tpl["Parameters"]["AlertEmail"]["Type"] == "String"
    t = res(tpl, "AlertTopic")
    assert t["Type"] == "AWS::SNS::Topic"
    subs = t["Properties"]["Subscription"]
    assert {"Protocol": "email", "Endpoint": {"Ref": "AlertEmail"}} in subs


def test_function_policies_scoped(tpl):
    pol = res(tpl, "ApiFunction")["Properties"]["Policies"]
    assert {"DynamoDBCrudPolicy": {"TableName": {"Ref": "EventTable"}}} in pol
    assert {"SNSPublishMessagePolicy": {"TopicName": {"Fn::GetAtt": ["AlertTopic", "TopicName"]}}} in pol


def test_cors_configuration(tpl):
    assert tpl["Parameters"]["DashboardOrigin"]["Type"] == "String"
    # CORS must live under Globals.HttpApi so it applies to the implicit API.
    # An explicit ServerlessHttpApi resource is ignored by SAM (CloudFormation
    # reports "No updates are to be performed" and the live CorsConfiguration is null).
    assert "ServerlessHttpApi" not in tpl.get("Resources", {})
    cors = tpl["Globals"]["HttpApi"]["CorsConfiguration"]
    origins = cors["AllowOrigins"]
    assert {"Ref": "DashboardOrigin"} in origins
    # API Gateway rejects duplicate origins. DashboardOrigin defaults to
    # http://localhost:3000, so no literal origin may equal that default.
    default_origin = tpl["Parameters"]["DashboardOrigin"]["Default"]
    literal_origins = [o for o in origins if isinstance(o, str)]
    assert default_origin not in literal_origins
    assert {"GET", "PUT"} <= set(cors["AllowMethods"])
    allowed_headers = {h.lower() for h in cors["AllowHeaders"]}
    assert {"content-type", "x-agentwatch-owner", "x-agentwatch-key-hash"} <= allowed_headers


def test_samconfig_region():
    assert 'region = "us-west-2"' in SAMCONFIG.read_text()
