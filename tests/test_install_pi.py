import unittest
from pathlib import Path

INSTALLER = Path(__file__).resolve().parents[1] / "scripts" / "install_pi.sh"


class PiInstallerTests(unittest.TestCase):
    def test_installs_and_exposes_search_tools(self) -> None:
        contents = INSTALLER.read_text()
        self.assertIn(
            "apt-get install -y curl ca-certificates ripgrep fd-find",
            contents,
        )
        self.assertIn('fdfind_path="$(command -v fdfind || true)"', contents)
        self.assertIn('ln -sfn "$fdfind_path" /usr/local/bin/fd', contents)
        self.assertIn("command -v rg", contents)
        self.assertIn("command -v fd", contents)


if __name__ == "__main__":
    unittest.main()
