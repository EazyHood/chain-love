import unittest
from pathlib import Path

from validate_csv import rule_provider_link_format

PROVIDERS = Path("references/providers/providers.csv")


def row(**cells):
    base = {
        "slug": "example",
        "website": "https://example.com/",
        "docs": "https://docs.example.com/",
        "x": "example",
        "github": "Chain-Love/chain-love",
        "discord": "invite/example",
        "telegram": "example",
        "linkedin": "company/example",
    }
    base.update(cells)
    return base


class TestProviderLinkFormat(unittest.TestCase):
    def test_valid_row_passes(self):
        self.assertEqual(rule_provider_link_format(PROVIDERS, [row()]), [])

    def test_blank_and_missing_cells_pass(self):
        rows = [
            row(website="", docs="", x="", github="", discord="", telegram="", linkedin=""),
            {"slug": "only-slug"},
            row(github=None),
        ]
        self.assertEqual(rule_provider_link_format(PROVIDERS, rows), [])

    def test_uppercase_scheme_and_http_pass(self):
        rows = [row(website="HTTPS://Example.com/", docs="http://docs.example.com/")]
        self.assertEqual(rule_provider_link_format(PROVIDERS, rows), [])

    def test_values_that_only_look_like_domains_pass(self):
        rows = [row(github="x.com-tools/repo", x="github", telegram="s/example", linkedin="in/someone")]
        self.assertEqual(rule_provider_link_format(PROVIDERS, rows), [])

    def test_other_csv_files_are_ignored(self):
        path = Path("references/offers/apis.csv")
        rows = [row(website="example.com", github="https://github.com/a/b")]
        self.assertEqual(rule_provider_link_format(path, rows), [])

    def test_fixture_named_providers_csv_is_ignored(self):
        path = Path("json-tools/tools/tests/fixtures/x/references/providers/providers.csv")
        self.assertEqual(rule_provider_link_format(path, [row(github="https://github.com/a/b")]), [])

    def test_hint_uses_the_column_example(self):
        errors = rule_provider_link_format(PROVIDERS, [row(x="https://x.com/1inch")])
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].endswith("(store only the part after the domain, e.g. '1inch')"))

    def test_website_and_docs_need_full_url(self):
        rows = [row(), row(website="example.com", docs="www.example.com/docs")]
        errors = rule_provider_link_format(PROVIDERS, rows)
        self.assertEqual(
            errors,
            [
                f"{PROVIDERS}: row 3: column 'website': 'example.com' must be a full URL starting with http:// or https://",
                f"{PROVIDERS}: row 3: column 'docs': 'www.example.com/docs' must be a full URL starting with http:// or https://",
            ],
        )

    def test_url_with_spaces_fails(self):
        errors = rule_provider_link_format(PROVIDERS, [row(docs="https://example.com/a b")])
        self.assertEqual(len(errors), 1)
        self.assertIn("column 'docs'", errors[0])

    def test_platform_full_url_fails(self):
        errors = rule_provider_link_format(PROVIDERS, [row(github="https://github.com/Chain-Love/chain-love")])
        self.assertEqual(
            errors,
            [
                f"{PROVIDERS}: row 2: column 'github': 'https://github.com/Chain-Love/chain-love' must not include a URL scheme"
                " (store only the part after the domain, e.g. 'Chain-Love/chain-love')"
            ],
        )

    def test_platform_domain_without_scheme_fails(self):
        rows = [
            row(
                x="X.com/example",
                discord="discord.gg/example",
                telegram="t.me/example",
                linkedin="www.linkedin.com/company/example",
            ),
            row(x="twitter.com/example", linkedin="uk.linkedin.com/company/example", github="GitHub.com/a/b"),
        ]
        errors = rule_provider_link_format(PROVIDERS, rows)
        self.assertEqual(len(errors), 7)
        for err in errors:
            self.assertIn("must not include the platform domain", err)

    def test_markdown_link_fails_in_every_link_column(self):
        md = "[Site](https://example.com)"
        rows = [row(website=md, docs=md, x=md, github=md, discord=md, telegram=md, linkedin=md)]
        errors = rule_provider_link_format(PROVIDERS, rows)
        self.assertEqual(len(errors), 7)
        for err in errors:
            self.assertIn("must be a plain value, not a Markdown link", err)

    def test_free_text_columns_are_not_checked(self):
        rows = [row(description="See [docs](https://example.com) for details")]
        self.assertEqual(rule_provider_link_format(PROVIDERS, rows), [])


if __name__ == "__main__":
    unittest.main()
