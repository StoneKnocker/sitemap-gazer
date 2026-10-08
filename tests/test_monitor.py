import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sitemap_gazer.core.crawl import FetchedSitemap, crawl_site
from sitemap_gazer.core.diff import assess_crawl, real_failures
from sitemap_gazer.core.run import _baseline_count, run
from sitemap_gazer.models import SitemapGazerConfig, Site
from sitemap_gazer.store import (
    SiteState,
    filter_signature,
    known_path,
    load_baseline,
    load_known,
    read_changes,
    state_path,
    write_known,
    write_state,
)
from sitemap_gazer.urls import filter_urls, group_urls, normalize_url, strip_locale
from usp.objects.sitemap import InvalidSitemap


def _site(**kwargs) -> Site:
    values = {"name": "example", "url": "https://example.com/"}
    values.update(kwargs)
    return Site(**values)


def _config(tmp: Path, sites: list[Site], **kwargs) -> SitemapGazerConfig:
    return SitemapGazerConfig(
        sites=sites, output_dir=tmp / "data", genReadme=True, **kwargs
    )


class UrlTests(unittest.TestCase):
    def test_normalize_drops_fragment_host_case_and_trailing_slash(self):
        self.assertEqual(
            normalize_url("HTTPS://Example.COM/Foo/#section"),
            "https://example.com/Foo",
        )

    def test_strip_locale_collapses_language_prefix(self):
        self.assertEqual(
            strip_locale("https://pollo.ai/fr/im/nano"),
            "https://pollo.ai/im/nano",
        )
        self.assertEqual(strip_locale("https://pollo.ai/fr"), "https://pollo.ai/")
        self.assertEqual(
            strip_locale("https://pollo.ai/pt-br/im/nano"),
            "https://pollo.ai/im/nano",
        )
        self.assertEqual(
            strip_locale("https://pollo.ai/im/nano"),
            "https://pollo.ai/im/nano",
        )

    def test_include_and_exclude(self):
        site = _site(include=["/models/"], exclude=["/draft"])
        kept = filter_urls(
            [
                "https://example.com/models/a",
                "https://example.com/models/a/draft",
                "https://example.com/blog/a",
            ],
            site,
        )
        self.assertEqual(kept, {"https://example.com/models/a"})

    def test_invalid_pattern_raises(self):
        with self.assertRaises(ValueError):
            filter_urls(["https://example.com/"], _site(include=["("]))

    def test_group_suffixes(self):
        grouped = group_urls(
            [
                "https://fal.ai/models/flux",
                "https://fal.ai/models/flux/api",
                "https://fal.ai/models/flux/examples",
                "https://fal.ai/other",
            ],
            ["/api", "/examples"],
        )
        self.assertEqual(
            grouped,
            [
                ("https://fal.ai/models/flux", ["/api", "/examples"]),
                ("https://fal.ai/other", []),
            ],
        )


class GuardTests(unittest.TestCase):
    def test_recursion_and_duplicate_failures_are_ignored(self):
        failures = [
            ("https://example.com/a.xml", "Recursion detected in URL"),
            ("https://example.com/b.xml", "Unable to fetch"),
        ]
        real = real_failures(failures, {"https://example.com/b.xml"})
        self.assertEqual(real, [])

    def test_empty_crawl_is_rejected(self):
        decision = assess_crawl(
            page_count=0,
            failures=[],
            success_urls=set(),
            state=None,
            ratio_reliable=True,
            min_page_ratio=0.8,
        )
        self.assertFalse(decision.accept)

    def test_shrink_below_ratio_is_rejected(self):
        state = SiteState(last_good_count=100, filter_signature="x")
        decision = assess_crawl(
            page_count=79,
            failures=[],
            success_urls=set(),
            state=state,
            ratio_reliable=True,
            min_page_ratio=0.8,
        )
        self.assertFalse(decision.accept)

    def test_count_at_ratio_is_accepted(self):
        state = SiteState(last_good_count=100, filter_signature="x")
        decision = assess_crawl(
            page_count=80,
            failures=[],
            success_urls=set(),
            state=state,
            ratio_reliable=True,
            min_page_ratio=0.8,
        )
        self.assertTrue(decision.accept)
        self.assertEqual(decision.reason, "")

    def test_second_large_crawl_adopts_the_new_count(self):
        adopted, pending, note = _baseline_count(4, 0, 20, 0.8)
        self.assertEqual(adopted, 4)
        self.assertEqual(pending, 20)
        self.assertIn("left unchanged", note)
        adopted, pending, note = _baseline_count(4, 20, 20, 0.8)
        self.assertEqual((adopted, pending, note), (20, 0, ""))

    def test_failed_sitemap_warns_without_rejecting_a_full_crawl(self):
        state = SiteState(last_good_count=100, filter_signature="x")
        decision = assess_crawl(
            page_count=100,
            failures=[("https://example.com/missing.xml", "Unable to fetch")],
            success_urls=set(),
            state=state,
            ratio_reliable=True,
            min_page_ratio=0.8,
        )
        self.assertTrue(decision.accept)
        self.assertIn("missing.xml", decision.reason)


class CrawlTargetTests(unittest.TestCase):
    def test_homepage_discovery_does_not_probe_known_paths(self):
        class Page:
            def __init__(self, url):
                self.url = url

        class Node:
            def __init__(self, url, pages=None, children=None):
                self.url = url
                self.pages = pages or []
                self.sub_sitemaps = children or []

        root = Node(
            "https://example.com/robots.txt",
            children=[
                Node(
                    "https://example.com/sitemap.xml",
                    pages=[Page("https://example.com/a")],
                )
            ],
        )
        with patch(
            "sitemap_gazer.core.crawl.sitemap_tree_for_homepage", return_value=root
        ) as homepage:
            fetched = crawl_site(_site())
        homepage.assert_called_once_with(
            "https://example.com/", use_known_paths=False, use_robots=True
        )
        self.assertEqual(fetched.urls, {"https://example.com/a"})

    def test_explicit_sitemap_url_skips_homepage_discovery(self):
        class Page:
            def __init__(self, url):
                self.url = url

        class Node:
            def __init__(self, url):
                self.url = url
                self.pages = [Page("https://example.com/only")]
                self.sub_sitemaps = []

        fetcher = type("Fetcher", (), {})()
        fetcher.sitemap = lambda: Node("https://example.com/sitemap.xml")
        with (
            patch(
                "sitemap_gazer.core.crawl.SitemapFetcher", return_value=fetcher
            ) as fetch,
            patch("sitemap_gazer.core.crawl.sitemap_tree_for_homepage") as homepage,
        ):
            fetched = crawl_site(_site(sitemap_url="https://example.com/sitemap.xml"))
        fetch.assert_called_once_with(
            url="https://example.com/sitemap.xml", recursion_level=0
        )
        homepage.assert_not_called()
        self.assertEqual(fetched.urls, {"https://example.com/only"})

    def test_invalid_child_is_recorded(self):
        class Node:
            def __init__(self):
                self.url = "https://example.com/sitemap.xml"
                self.pages = []
                self.sub_sitemaps = [
                    InvalidSitemap(
                        "https://example.com/child.xml", "Unable to fetch child"
                    )
                ]

        with patch(
            "sitemap_gazer.core.crawl.sitemap_tree_for_homepage", return_value=Node()
        ):
            fetched = crawl_site(_site())
        self.assertEqual(
            fetched.failures,
            [("https://example.com/child.xml", "Unable to fetch child")],
        )


class RunTests(unittest.TestCase):
    def _fetched(self, *urls, failures=None):
        return FetchedSitemap(
            urls=set(urls),
            failures=failures or [],
            sitemap_urls={"https://example.com/sitemap.xml"},
        )

    def test_initial_crawl_is_not_reported_as_new(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site = _site()
            calls = {"n": 0}

            def crawl(_site):
                calls["n"] += 1
                if calls["n"] == 1:
                    return self._fetched(
                        "https://example.com/a", "https://example.com/b"
                    )
                return self._fetched(
                    "https://example.com/a",
                    "https://example.com/b/",
                    "https://example.com/c",
                )

            config = _config(root, [site])
            first = run(config, cwd=root, crawl_fn=crawl, timestamp="20261008_010101")
            second = run(config, cwd=root, crawl_fn=crawl, timestamp="20261008_020202")

        self.assertEqual(first[0].status, "initial")
        self.assertEqual(first[0].new_urls, [])
        self.assertEqual(second[0].new_urls, ["https://example.com/c"])
        self.assertIn("1 new URLs", second[0].message)
        self.assertNotIn("https://example.com/c", first[0].message)

    def test_partial_crawl_does_not_replace_known_urls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seen = {"phase": "full"}

            def crawl(_site):
                if seen["phase"] == "full":
                    return self._fetched(
                        *(f"https://example.com/{i}" for i in range(10))
                    )
                if seen["phase"] == "partial":
                    return self._fetched(
                        "https://example.com/0", "https://example.com/new"
                    )
                return self._fetched(*(f"https://example.com/{i}" for i in range(10)))

            config = _config(root, [_site()])
            run(config, cwd=root, crawl_fn=crawl, timestamp="20261008_010101")
            seen["phase"] = "partial"
            partial = run(config, cwd=root, crawl_fn=crawl, timestamp="20261008_020202")
            seen["phase"] = "again"
            again = run(config, cwd=root, crawl_fn=crawl, timestamp="20261008_030303")

            self.assertEqual(partial[0].status, "skipped")
            self.assertEqual(again[0].new_urls, [])
            known = load_known(root / "data" / "example" / "known_urls.txt.gz")
            self.assertEqual(len(known), 10)
            self.assertNotIn("https://example.com/new", known)

    def test_project_readme_is_left_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "README.md"
            project.write_text("# sitemap-gazer\n\nProject docs.\n", encoding="utf-8")
            taken = root / "data" / "README.md"
            taken.parent.mkdir()
            taken.write_text("# notes\n", encoding="utf-8")

            run(
                _config(root, [_site()]),
                cwd=root,
                crawl_fn=lambda _site: self._fetched("https://example.com/a"),
                timestamp="20261008_010101",
            )

            self.assertEqual(
                project.read_text(encoding="utf-8"),
                "# sitemap-gazer\n\nProject docs.\n",
            )
            self.assertEqual(taken.read_text(encoding="utf-8"), "# notes\n")
            report = (root / "data" / "sitemap-report.md").read_text(encoding="utf-8")
            self.assertTrue(report.startswith("# Sitemap Gazer Report"))

    def test_one_site_failure_does_not_stop_the_other(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def crawl(site):
                if site.name == "bad":
                    raise RuntimeError("boom")
                return self._fetched("https://example.com/ok")

            config = _config(
                root,
                [_site(name="bad"), _site(name="good", url="https://good.example/")],
            )
            results = run(config, cwd=root, crawl_fn=crawl, timestamp="20261008_010101")
            readme = (root / "data" / "README.md").read_text(encoding="utf-8")

        self.assertEqual([result.status for result in results], ["error", "initial"])
        self.assertIn("boom", results[0].message)
        self.assertIn("bad: failed: boom", readme)
        self.assertIn("good: initial crawl", readme)

    def test_locale_copies_count_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            phase = {"n": 0}

            def crawl(_site):
                phase["n"] += 1
                if phase["n"] == 1:
                    return self._fetched("https://pollo.ai/im/nano")
                return self._fetched(
                    "https://pollo.ai/im/nano",
                    "https://pollo.ai/fr/im/nano",
                    "https://pollo.ai/ja/im/other",
                )

            config = _config(root, [_site(name="pollo", strip_locales=True)])
            run(config, cwd=root, crawl_fn=crawl, timestamp="20261008_010101")
            second = run(config, cwd=root, crawl_fn=crawl, timestamp="20261008_020202")

            self.assertEqual(second[0].new_urls, ["https://pollo.ai/im/other"])

    def test_readme_groups_suffixes_and_keeps_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pages = [
                [
                    "https://fal.ai/models/flux",
                    "https://fal.ai/models/flux/api",
                ],
                [
                    "https://fal.ai/models/flux",
                    "https://fal.ai/models/flux/api",
                    "https://fal.ai/models/flux/examples",
                    "https://fal.ai/startups",
                ],
            ]

            def crawl(_site):
                return self._fetched(*pages.pop(0))

            config = _config(
                root,
                [_site(name="fal", group_suffixes=["/api", "/examples"])],
            )
            run(config, cwd=root, crawl_fn=crawl, timestamp="20261008_010101")
            run(config, cwd=root, crawl_fn=crawl, timestamp="20261008_020202")
            text = (root / "data" / "README.md").read_text(encoding="utf-8")
            records = read_changes(root / "data" / "fal" / "changes.jsonl", limit=10)

        self.assertIn("### 20261008_020202", text)
        self.assertIn("- https://fal.ai/models/flux", text)
        self.assertIn("  - /examples", text)
        self.assertIn("- https://fal.ai/startups", text)
        self.assertNotIn("### 20261008_010101", text)
        self.assertEqual(records[0]["timestamp"], "20261008_020202")


class InitTests(unittest.TestCase):
    def test_creates_a_loadable_config(self):
        from sitemap_gazer.core.init import create_config_file, load_config_file

        with tempfile.TemporaryDirectory() as tmp:
            path = create_config_file(tmp)
            config = load_config_file(path)
            self.assertTrue(path.name == "sitemap-gazer.json")
        self.assertEqual(config.sites, [])
        self.assertTrue(config.genReadme)
        self.assertEqual(config.min_page_ratio, 0.8)


class MigrationTests(unittest.TestCase):
    def test_union_of_snapshots_becomes_the_known_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            site_dir = Path(tmp) / "pollo"
            self._snapshot(
                site_dir / "20260101_000000",
                ["https://pollo.ai/a", "https://pollo.ai/old"],
            )
            self._snapshot(
                site_dir / "20260201_000000",
                ["https://pollo.ai/a", "https://pollo.ai/b"],
            )
            site = _site(name="pollo", strip_locales=True)
            baseline = load_baseline(site, site_dir)

        self.assertEqual(
            baseline.known,
            {
                "https://pollo.ai/a",
                "https://pollo.ai/old",
                "https://pollo.ai/b",
            },
        )
        self.assertEqual(baseline.state.last_good_count, 2)
        self.assertIn("2 existing snapshots", baseline.note)

    def test_seeded_history_is_not_reported_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site_dir = root / "data" / "pollo"
            self._snapshot(site_dir / "20260101_000000", ["https://pollo.ai/old"])
            self._snapshot(site_dir / "20260201_000000", ["https://pollo.ai/current"])

            def crawl(_site):
                return FetchedSitemap(
                    urls={
                        "https://pollo.ai/old",
                        "https://pollo.ai/current",
                        "https://pollo.ai/new",
                    },
                    sitemap_urls={"https://pollo.ai/sitemap.xml"},
                )

            config = _config(root, [_site(name="pollo")])
            results = run(config, cwd=root, crawl_fn=crawl, timestamp="20261008_010101")

        self.assertEqual(results[0].new_urls, ["https://pollo.ai/new"])
        self.assertNotEqual(results[0].status, "initial")

    def test_locale_filter_applies_when_seeding(self):
        with tempfile.TemporaryDirectory() as tmp:
            site_dir = Path(tmp) / "pollo"
            self._snapshot(
                site_dir / "20260101_000000",
                ["https://pollo.ai/im/nano", "https://pollo.ai/fr/im/nano"],
            )
            baseline = load_baseline(_site(name="pollo", strip_locales=True), site_dir)
        self.assertEqual(baseline.known, {"https://pollo.ai/im/nano"})
        self.assertEqual(baseline.state.last_good_count, 1)

    def test_filter_change_reapplies_to_stored_urls(self):
        with tempfile.TemporaryDirectory() as tmp:
            site_dir = Path(tmp) / "pollo.ai"
            site_dir.mkdir()
            plain = _site(name="pollo.ai", url="https://pollo.ai/", strip_locales=False)
            write_known(
                known_path(site_dir),
                {
                    "https://pollo.ai/im/nano",
                    "https://pollo.ai/fr/im/nano",
                    "https://pollo.ai/ja/im/other",
                },
            )
            write_state(
                state_path(site_dir),
                SiteState(
                    last_good_count=3,
                    filter_signature=filter_signature(plain),
                    sitemap_urls=["https://pollo.ai/sitemap.xml"],
                ),
            )
            baseline = load_baseline(
                _site(name="pollo.ai", url="https://pollo.ai/", strip_locales=True),
                site_dir,
            )

        self.assertEqual(
            baseline.known,
            {"https://pollo.ai/im/nano", "https://pollo.ai/im/other"},
        )
        self.assertEqual(baseline.state.last_good_count, 2)
        self.assertTrue(baseline.ratio_reliable)

    def test_latest_snapshot_sets_the_baseline_not_the_largest(self):
        with tempfile.TemporaryDirectory() as tmp:
            site_dir = Path(tmp) / "higgsfield"
            self._snapshot(
                site_dir / "20260525_093001",
                [f"https://higgsfield.ai/{i}" for i in range(20)],
            )
            self._snapshot(
                site_dir / "20260806_093024",
                [f"https://higgsfield.ai/{i}" for i in range(5)],
            )
            baseline = load_baseline(
                _site(name="higgsfield", url="https://higgsfield.ai/"), site_dir
            )
        self.assertEqual(baseline.state.last_good_count, 5)
        self.assertEqual(len(baseline.known), 20)

    def _snapshot(self, directory: Path, urls: list[str]) -> None:
        directory.mkdir(parents=True)
        payload = {
            "url": "https://pollo.ai/",
            "type": "IndexWebsiteSitemap",
            "pages": [],
            "sitemaps": [
                {
                    "url": "https://pollo.ai/sitemap.xml",
                    "type": "PagesXMLSitemap",
                    "pages": [{"url": url} for url in urls],
                    "sitemaps": [],
                }
            ],
        }
        (directory / "sitemap.json").write_text(json.dumps(payload), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
