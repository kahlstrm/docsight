"""E2E tests for internationalization (language switching)."""

import json
from pathlib import Path

import pytest

EUROPEAN_LANGUAGE_PACK = {
    "bg", "cs", "da", "de", "el", "en", "es", "et", "fi", "fr",
    "ga", "hr", "hu", "it", "lt", "lv", "nb", "nl", "pl", "pt",
    "ro", "sk", "sl", "sv",
}


def _stored_language(server):
    config_path = Path(server["data_dir"]) / "config.json"
    return json.loads(config_path.read_text(encoding="utf-8"))["language"]


class TestLanguageSwitching:
    """Language can be switched via ?lang= query parameter."""

    def test_default_language_is_english(self, demo_page):
        lang = demo_page.locator("html").get_attribute("lang")
        assert lang == "en"

    def test_switch_to_german(self, page, live_server):
        page.goto(f"{live_server}/?lang=de")
        lang = page.locator("html").get_attribute("lang")
        assert lang == "de"

    def test_switch_to_french(self, page, live_server):
        page.goto(f"{live_server}/?lang=fr")
        lang = page.locator("html").get_attribute("lang")
        assert lang == "fr"

    def test_switch_to_spanish(self, page, live_server):
        page.goto(f"{live_server}/?lang=es")
        lang = page.locator("html").get_attribute("lang")
        assert lang == "es"

    def test_settings_respects_lang_param(self, page, live_server):
        page.goto(f"{live_server}/settings?lang=de")
        lang = page.locator("html").get_attribute("lang")
        assert lang == "de"

    def test_switch_to_new_european_language(self, page, live_server):
        page.goto(f"{live_server}/?lang=it")
        lang = page.locator("html").get_attribute("lang")
        assert lang == "it"

    def test_settings_language_selector_lists_european_pack(self, page, live_server):
        page.goto(f"{live_server}/settings?lang=pl")
        page.evaluate("switchSection('general')")
        values = page.locator("#language option").evaluate_all("opts => opts.map(o => o.value)")
        assert set(values) == EUROPEAN_LANGUAGE_PACK

    @pytest.mark.parametrize("width,height", [(1280, 900), (390, 844)])
    def test_settings_language_selector_does_not_overflow_viewport(self, page, live_server, width, height):
        page.set_viewport_size({"width": width, "height": height})
        page.goto(f"{live_server}/settings?lang=nb")
        page.evaluate("switchSection('general')")
        page.locator("#language").scroll_into_view_if_needed()
        metrics = page.evaluate(
            """() => ({
                viewport: window.innerWidth,
                doc: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
                selectorRight: document.querySelector('#language').getBoundingClientRect().right,
            })"""
        )
        assert metrics["doc"] <= metrics["viewport"]
        assert metrics["selectorRight"] <= metrics["viewport"]


class TestFirstRunLanguageInference:
    """First-run browser inference is isolated from shared demo fixtures."""

    @pytest.mark.parametrize(
        ("accept_language", "expected"),
        [
            ("de-DE,de;q=0.9", "de"),
            ("en-US,en;q=0.9", "en"),
            ("zz-ZZ,xx;q=0.9", "en"),
        ],
    )
    def test_fresh_setup_infers_and_persists_browser_language(
        self, browser, isolated_setup_server, accept_language, expected
    ):
        context = browser.new_context(
            extra_http_headers={"Accept-Language": accept_language}
        )
        try:
            page = context.new_page()
            page.goto(isolated_setup_server["url"] + "/setup")

            assert page.locator("html").get_attribute("lang") == expected
            assert page.locator("#lang-select").input_value() == expected
            assert _stored_language(isolated_setup_server) == expected
        finally:
            context.close()

    def test_explicit_setup_override_persists_across_header_change(
        self, browser, isolated_setup_server
    ):
        context = browser.new_context(
            extra_http_headers={"Accept-Language": "de-DE"}
        )
        try:
            page = context.new_page()
            page.goto(isolated_setup_server["url"] + "/setup")
            assert page.locator("html").get_attribute("lang") == "de"

            page.goto(isolated_setup_server["url"] + "/setup?lang=fr")

            assert page.locator("html").get_attribute("lang") == "fr"
            assert page.locator("#lang-select").input_value() == "fr"
            assert _stored_language(isolated_setup_server) == "fr"

            page.set_extra_http_headers({"Accept-Language": "en-US"})
            page.goto(isolated_setup_server["url"] + "/setup")

            assert page.locator("html").get_attribute("lang") == "fr"
            assert page.locator("#lang-select").input_value() == "fr"
            assert _stored_language(isolated_setup_server) == "fr"
        finally:
            context.close()
