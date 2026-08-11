import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from run_agent import _copy_openhands_trajectories, _write_openhands_log


class OpenHandsTrajectoryTests(unittest.TestCase):
    def test_process_output_is_written_to_attempt_log(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "attempt_1.log"

            _write_openhands_log(output_file, "agent output\n", "agent error\n")

            self.assertEqual(
                output_file.read_text(),
                "agent output\n\n--- stderr ---\nagent error\n",
            )

    @patch("run_agent.subprocess.run")
    def test_json_trajectory_copy_uses_the_trajectory_directory(self, run):
        run.return_value.returncode = 0

        copied = _copy_openhands_trajectories("container-id", Path("local"))

        self.assertTrue(copied)
        run.assert_called_once_with(
            ["docker", "cp", "container-id:/agent_trajectory/.", "local"],
            capture_output=True,
            text=True,
        )

    @patch("run_agent.subprocess.run")
    def test_json_trajectory_copy_reports_failure(self, run):
        run.return_value.returncode = 1
        run.return_value.stderr = "source is not a directory"
        run.return_value.stdout = ""

        copied = _copy_openhands_trajectories("container-id", Path("local"))

        self.assertFalse(copied)


if __name__ == "__main__":
    unittest.main()
