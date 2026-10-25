"""Dry-run RPC: prints what would be sent to the robot and returns plausible stock replies."""
import os

from .rpc import MasterPiRPC


class DryRunRPC(MasterPiRPC):
    def call(self, method, *params, tolerate_error=False):
        print(f"  [dry-run] {method}{tuple(params)}")
        if method == "GetBatteryVoltage":
            return [True, 7800, method]
        if method == "GetSonarDistance":
            return [True, 250, method]
        return [True, [], method]

    def snapshot(self):
        # Optional fake camera frame for testing the vision path: MASTERPI_DRY_SNAPSHOT=/path/to.jpg
        path = os.environ.get("MASTERPI_DRY_SNAPSHOT")
        return open(path, "rb").read() if path else None
