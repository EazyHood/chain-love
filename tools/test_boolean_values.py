import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from validate_csv import (
    CSVValidator,
    boolean_columns_by_file,
    rule_boolean_values,
)

SCRIPT = Path(__file__).resolve().parent / "validate_csv.py"


def write_csv(root: Path, relative: str, lines: list[str]) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")
    return path


class TestBooleanColumnsFromSchema(unittest.TestCase):
    def test_columns_come_from_schema(self):
        columns = boolean_columns_by_file()
        self.assertIn("evm", columns["wallets"])
        self.assertIn("keyExport", columns["wallets"])
        self.assertIn("requiresLogin", columns["faucets"])
        self.assertIn("hasCaptcha", columns["faucets"])
        self.assertIn("trial", columns["apis"])
        self.assertIn("aggregator", columns["ramps"])
        self.assertIn("starred", columns["providers"])

    def test_non_boolean_columns_are_not_listed(self):
        columns = boolean_columns_by_file()
        self.assertNotIn("slug", columns["wallets"])
        self.assertNotIn("description", columns["wallets"])
        self.assertNotIn("price", columns["faucets"])


class TestRuleBooleanValues(unittest.TestCase):
    def run_rule(self, relative: str, lines: list[str]) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_csv(Path(tmp), relative, lines)
            validator = CSVValidator()
            validator.add_rule(rule_boolean_values)
            errors = validator.validate_file(path)
            return [e.replace(str(path), relative) for e in errors]

    def test_uppercase_values_pass(self):
        errors = self.run_rule("references/offers/faucets.csv", [
            "slug,requiresLogin,hasCaptcha,starred",
            "a-faucet,TRUE,FALSE,FALSE",
            "b-faucet,FALSE,TRUE,TRUE",
        ])
        self.assertEqual(errors, [])

    def test_blank_cells_pass(self):
        # Blank listing cells inherit the canonical value
        errors = self.run_rule("listings/specific-networks/algorand/faucets.csv", [
            "slug,offer,requiresLogin,hasCaptcha,starred",
            "a-faucet-testnet,!offer:a-faucet,,,",
        ])
        self.assertEqual(errors, [])

    def test_override_with_uppercase_passes(self):
        errors = self.run_rule("listings/all-networks/wallets.csv", [
            "slug,offer,evm,staking",
            "a-wallet,!offer:a-wallet,TRUE,",
        ])
        self.assertEqual(errors, [])

    def test_lowercase_and_mixed_case_fail(self):
        errors = self.run_rule("listings/specific-networks/algorand/wallets.csv", [
            "slug,offer,evm,staking,starred",
            "a-wallet,!offer:a-wallet,true,False,FALSE",
            "b-wallet,!offer:b-wallet,TRUE,FALSE,True",
        ])
        self.assertEqual(errors, [
            "listings/specific-networks/algorand/wallets.csv: row 2: column 'evm': "
            "boolean value must be TRUE or FALSE (uppercase), got 'true'",
            "listings/specific-networks/algorand/wallets.csv: row 2: column 'staking': "
            "boolean value must be TRUE or FALSE (uppercase), got 'False'",
            "listings/specific-networks/algorand/wallets.csv: row 3: column 'starred': "
            "boolean value must be TRUE or FALSE (uppercase), got 'True'",
        ])

    def test_other_values_fail(self):
        errors = self.run_rule("references/offers/apis.csv", [
            "slug,starred,trial",
            "a-api,yes,1",
            "b-api,null, TRUE",
            'c-api,"[""TRUE""]",FALSE',
        ])
        self.assertEqual(len(errors), 5)
        self.assertIn("row 2: column 'starred'", errors[0])
        self.assertIn("got 'yes'", errors[0])
        self.assertIn("row 2: column 'trial'", errors[1])
        self.assertIn("row 3: column 'starred'", errors[2])
        self.assertIn("got 'null'", errors[2])
        self.assertIn("got ' TRUE'", errors[3])
        self.assertIn("row 4: column 'starred'", errors[4])

    def test_providers_file_is_checked(self):
        errors = self.run_rule("references/providers/providers.csv", [
            "slug,name,starred",
            "a,A,FALSE",
            "b,B,false",
        ])
        self.assertEqual(len(errors), 1)
        self.assertIn("row 3: column 'starred'", errors[0])

    def test_non_boolean_columns_are_ignored(self):
        errors = self.run_rule("references/offers/wallets.csv", [
            "slug,description,evm",
            "a-wallet,true,TRUE",
        ])
        self.assertEqual(errors, [])

    def test_files_outside_schema_are_ignored(self):
        errors = self.run_rule("outreach/registry.csv", [
            "slug,starred",
            "a,true",
        ])
        self.assertEqual(errors, [])

    def test_missing_column_and_empty_file_pass(self):
        self.assertEqual(self.run_rule("references/offers/wallets.csv", [
            "slug,description",
            "a-wallet,desc",
        ]), [])
        self.assertEqual(self.run_rule("references/offers/wallets.csv", [
            "slug,evm",
        ]), [])


class TestValidateCsvMain(unittest.TestCase):
    def run_script(self, lines: list[str]) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as tmp:
            write_csv(Path(tmp), "references/offers/wallets.csv", lines)
            return subprocess.run(
                [sys.executable, str(SCRIPT)],
                cwd=tmp,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )

    def test_main_reports_bad_boolean(self):
        result = self.run_script(["slug,evm", "a-wallet,true"])
        self.assertEqual(result.returncode, 1)
        self.assertIn("row 2: column 'evm'", result.stdout)
        self.assertIn("got 'true'", result.stdout)

    def test_main_passes_uppercase(self):
        result = self.run_script(["slug,evm", "a-wallet,TRUE"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("All checks passed.", result.stdout)


if __name__ == "__main__":
    unittest.main()
