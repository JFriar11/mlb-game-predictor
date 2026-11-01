"""Check the compiled Azure preparation template's deployment-safety defaults."""

import json
import sys
from pathlib import Path


def main() -> None:
    template = json.loads(Path(sys.argv[1]).read_text())
    resources = {item["type"]: item for item in template["resources"]}
    assert set(resources) == {"Microsoft.App/containerApps", "Microsoft.App/jobs"}
    app = resources["Microsoft.App/containerApps"]["properties"]
    worker = resources["Microsoft.App/jobs"]["properties"]
    assert app["configuration"]["ingress"]["external"] is False
    assert app["configuration"]["ingress"]["allowInsecure"] is False
    assert app["template"]["scale"]["minReplicas"] == 0
    assert app["template"]["scale"]["maxReplicas"] == 2
    assert worker["configuration"]["triggerType"] == "Manual"
    assert "scheduleTriggerConfig" not in worker["configuration"]
    assert worker["configuration"]["manualTriggerConfig"]["parallelism"] == 1
    container = worker["template"]["containers"][0]
    assert container["command"] == ["mlb-predictor"]
    assert container["args"] == ["watcher-status"]
    for parameter in ("apiDatabaseUrl", "workerDatabaseUrl", "registryPassword"):
        assert template["parameters"][parameter]["type"].lower() == "securestring"
        assert "defaultValue" not in template["parameters"][parameter]
    for configuration in (app, worker):
        env = configuration["template"]["containers"][0]["env"]
        assert env == [{"name": "MLB_DATABASE_URL", "secretRef": "database-url"}]
    assert set(template["outputs"]) == {"appResourceId", "workerResourceId"}
    print("PASS: private ingress, no timer/polling, separate secret references, bounded scaling")


if __name__ == "__main__":
    main()
