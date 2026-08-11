import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from utils import get_llm_env


class GetLlmEnvTests(unittest.TestCase):
    def test_direct_openai_configuration_has_budget(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True):
            env, model = get_llm_env(
                model_provider="openai",
                openai_model_id="gpt-5.6-sol",
                max_budget_per_task=10.0,
            )

        self.assertEqual(model, "openai/gpt-5.6-sol")
        self.assertEqual(env["LLM_MODEL"], "openai/gpt-5.6-sol")
        self.assertEqual(env["LLM_API_KEY"], "test-key")
        self.assertEqual(env["OPENAI_API_KEY"], "test-key")
        self.assertEqual(env["MAX_BUDGET_PER_TASK"], "10.0")
        self.assertEqual(env["LLM_INPUT_COST_PER_TOKEN"], "5e-06")
        self.assertEqual(env["LLM_OUTPUT_COST_PER_TOKEN"], "3e-05")
        self.assertEqual(env["LLM_REASONING_EFFORT"], "none")
        self.assertEqual(env["LLM_DISABLE_STOP_WORD"], "true")
        self.assertEqual(env["LLM_DROP_PARAMS"], "true")
        self.assertNotIn("OPENAI_BASE_URL", env)

    def test_anthropic_configuration_has_budget(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=True):
            env, model = get_llm_env(
                model_provider="anthropic",
                anthropic_model_id="claude-opus-4-6",
                max_budget_per_task=10.0,
            )

        self.assertEqual(model, "claude-opus-4-6")
        self.assertEqual(env["LLM_MODEL"], "claude-opus-4-6")
        self.assertEqual(env["LLM_API_KEY"], "test-key")
        self.assertEqual(env["ANTHROPIC_API_KEY"], "test-key")
        self.assertEqual(env["MAX_BUDGET_PER_TASK"], "10.0")

    def test_deepseek_configuration_has_provider_model_and_budget(self):
        deepseek_env = {
            "DEEPSEEK_API_KEY": "test-key",
            "DEEPSEEK_BASE_URL": "https://deepseek.example",
        }
        with patch.dict(os.environ, deepseek_env, clear=True):
            env, model = get_llm_env(
                model_provider="deepseek",
                deepseek_model_id="deepseek-v4-pro",
                max_budget_per_task=10.0,
            )

        self.assertEqual(model, "deepseek/deepseek-v4-pro")
        self.assertEqual(env["LLM_MODEL"], "deepseek/deepseek-v4-pro")
        self.assertEqual(env["LLM_API_KEY"], "test-key")
        self.assertEqual(env["DEEPSEEK_API_KEY"], "test-key")
        self.assertEqual(env["LLM_BASE_URL"], "https://deepseek.example")
        self.assertEqual(env["DEEPSEEK_BASE_URL"], "https://deepseek.example")
        self.assertEqual(env["MAX_BUDGET_PER_TASK"], "10.0")
        self.assertEqual(env["LLM_REASONING_EFFORT"], "high")
        self.assertEqual(env["LLM_INPUT_COST_PER_TOKEN"], "4.35e-7")
        self.assertEqual(env["LLM_OUTPUT_COST_PER_TOKEN"], "8.7e-7")
        self.assertEqual(env["LLM_DROP_PARAMS"], "true")

    def test_deepseek_uses_official_default_base_url(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}, clear=True):
            env, _ = get_llm_env(
                model_provider="deepseek",
                deepseek_model_id="deepseek-v4-flash",
            )

        self.assertEqual(env["LLM_BASE_URL"], "https://api.deepseek.com")
        self.assertEqual(env["LLM_INPUT_COST_PER_TOKEN"], "1.4e-7")
        self.assertEqual(env["LLM_OUTPUT_COST_PER_TOKEN"], "2.8e-7")

    def test_zero_budget_disables_openhands_limit(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True):
            env, _ = get_llm_env(
                model_provider="openai",
                openai_model_id="gpt-5.6-sol",
                max_budget_per_task=0,
            )

        self.assertEqual(env["MAX_BUDGET_PER_TASK"], "0")

    def test_unknown_provider_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown model provider"):
            get_llm_env(model_provider="unknown")


if __name__ == "__main__":
    unittest.main()
