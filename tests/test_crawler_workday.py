# tests/test_crawler_workday.py
"""Tests for src/crawlers/workday.py — WorkdayCrawler.

All HTTP calls and Playwright calls are mocked. No database access. No network calls.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.crawlers.exceptions import CrawlerFetchError, CrawlerParseError
from src.crawlers.workday import WorkdayCrawler, _parse_workday_url

_CXS_FIXTURE = Path(__file__).parent / "fixtures" / "workday_cxs_response.json"
_HTML_FIXTURE = Path(__file__).parent / "fixtures" / "workday_html_snapshot.html"

_BASE_CONFIG = {
    "workday_urls": {"TestCo": "https://testco.wd5.myworkdayjobs.com/en-US/TestCo"},
    "request_timeout_seconds": 10,
    "max_retries": 1,
    "user_agent": "TestBot/1.0",
}


def _load_cxs_fixture() -> dict:
    return json.loads(_CXS_FIXTURE.read_text())


def _load_html_fixture() -> str:
    return _HTML_FIXTURE.read_text()


def _mock_post_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    return resp


# ---------------------------------------------------------------------------
# _parse_workday_url — unit tests
# ---------------------------------------------------------------------------


def test_parse_workday_url_extracts_tenant_site_name_with_locale():
    base_url, tenant, site_name = _parse_workday_url(
        "https://atlassian.wd5.myworkdayjobs.com/en-US/Atlassian"
    )
    assert tenant == "atlassian"
    assert site_name == "Atlassian"
    assert base_url == "https://atlassian.wd5.myworkdayjobs.com"


def test_parse_workday_url_extracts_site_name_without_locale():
    base_url, tenant, site_name = _parse_workday_url(
        "https://company.wd3.myworkdayjobs.com/careers"
    )
    assert tenant == "company"
    assert site_name == "careers"
    assert base_url == "https://company.wd3.myworkdayjobs.com"


def test_parse_workday_url_raises_for_non_workday_domain():
    with pytest.raises(ValueError, match="Not a Workday URL"):
        _parse_workday_url("https://greenhouse.io/boards/jobs")


def test_parse_workday_url_raises_when_no_site_name_in_path():
    with pytest.raises(ValueError):
        _parse_workday_url("https://company.wd5.myworkdayjobs.com/en-US/")


# ---------------------------------------------------------------------------
# _parse_one_json — unit tests (no HTTP)
# ---------------------------------------------------------------------------


def test_parse_one_json_returns_job_dict_from_valid_item():
    crawler = WorkdayCrawler(_BASE_CONFIG)
    item = _load_cxs_fixture()["jobPostings"][0]
    job = crawler._parse_one_json(
        item, "TestCo", "https://testco.wd5.myworkdayjobs.com/en-US/TestCo"
    )
    assert job is not None
    assert job["title"] == "Senior Data Engineer"
    assert job["company"] == "TestCo"
    assert job["ats_job_id"] == "JR100001"
    assert job["source_name"] == "workday"


def test_parse_one_json_company_name_is_config_display_name_not_tenant():
    """company field must be the human-readable name from config, not the tenant slug."""
    crawler = WorkdayCrawler(_BASE_CONFIG)
    item = {"title": "Data Engineer", "externalPath": "/job/DE_JR001", "jobReqId": "JR001"}
    job = crawler._parse_one_json(
        item, "Acme Corporation", "https://acme.wd5.myworkdayjobs.com/en-US/Acme"
    )
    assert job["company"] == "Acme Corporation"


def test_parse_one_json_source_url_is_configured_url_plus_external_path():
    crawler = WorkdayCrawler(_BASE_CONFIG)
    item = {"title": "Data Engineer", "externalPath": "/job/DE_JR001", "jobReqId": "JR001"}
    job = crawler._parse_one_json(
        item, "TestCo", "https://testco.wd5.myworkdayjobs.com/en-US/TestCo"
    )
    assert job["source_url"] == "https://testco.wd5.myworkdayjobs.com/en-US/TestCo/job/DE_JR001"


def test_parse_one_json_returns_none_missing_title():
    crawler = WorkdayCrawler(_BASE_CONFIG)
    item = {"externalPath": "/job/DE_JR001", "jobReqId": "JR001"}
    assert crawler._parse_one_json(item, "TestCo", "https://testco.wd5.myworkdayjobs.com/en-US/TestCo") is None


def test_parse_one_json_returns_none_missing_external_path():
    crawler = WorkdayCrawler(_BASE_CONFIG)
    item = {"title": "Data Engineer", "jobReqId": "JR001"}
    assert crawler._parse_one_json(item, "TestCo", "https://testco.wd5.myworkdayjobs.com/en-US/TestCo") is None


def test_parse_one_json_ats_job_id_is_none_when_job_req_id_absent():
    crawler = WorkdayCrawler(_BASE_CONFIG)
    item = {"title": "Data Engineer", "externalPath": "/job/DE_JR001"}
    job = crawler._parse_one_json(item, "TestCo", "https://testco.wd5.myworkdayjobs.com/en-US/TestCo")
    assert job is not None
    assert job["ats_job_id"] is None


def test_parse_one_json_location_raw_is_locations_text():
    crawler = WorkdayCrawler(_BASE_CONFIG)
    item = {
        "title": "Data Engineer",
        "externalPath": "/job/DE_JR001",
        "locationsText": "Gurugram, India",
        "jobReqId": "JR001",
    }
    job = crawler._parse_one_json(item, "TestCo", "https://testco.wd5.myworkdayjobs.com/en-US/TestCo")
    assert job["location"] == "Gurugram, India"


def test_parse_one_json_description_is_always_none():
    """CXS list endpoint does not return job descriptions."""
    crawler = WorkdayCrawler(_BASE_CONFIG)
    item = {"title": "Data Engineer", "externalPath": "/job/DE_JR001", "jobReqId": "JR001"}
    job = crawler._parse_one_json(item, "TestCo", "https://testco.wd5.myworkdayjobs.com/en-US/TestCo")
    assert job["description"] is None


# ---------------------------------------------------------------------------
# _parse_one_html — unit tests (no HTTP, no Playwright)
# ---------------------------------------------------------------------------


def test_parse_one_html_returns_job_dict_from_valid_anchor():
    from bs4 import BeautifulSoup
    crawler = WorkdayCrawler(_BASE_CONFIG)
    soup = BeautifulSoup(_load_html_fixture(), "html.parser")
    link = soup.find("a", attrs={"data-automation-id": "jobPostingTitleLink"})
    job = crawler._parse_one_html(
        link, "TestCo", "https://testco.wd5.myworkdayjobs.com/en-US/TestCo"
    )
    assert job is not None
    assert job["title"] == "Senior Data Engineer"
    assert job["company"] == "TestCo"
    assert job["location"] == "Gurugram, India"
    assert job["ats_job_id"] == "JR100001"
    assert job["source_name"] == "workday"


def test_parse_one_html_company_name_is_config_display_name():
    """company field must be the human-readable name passed in, not derived from URL."""
    from bs4 import BeautifulSoup
    crawler = WorkdayCrawler(_BASE_CONFIG)
    soup = BeautifulSoup(_load_html_fixture(), "html.parser")
    link = soup.find("a", attrs={"data-automation-id": "jobPostingTitleLink"})
    job = crawler._parse_one_html(link, "Acme Corporation", "https://acme.wd5.myworkdayjobs.com/en-US/Acme")
    assert job["company"] == "Acme Corporation"


def test_parse_one_html_source_url_constructed_from_relative_href():
    from bs4 import BeautifulSoup
    crawler = WorkdayCrawler(_BASE_CONFIG)
    soup = BeautifulSoup(_load_html_fixture(), "html.parser")
    link = soup.find("a", attrs={"data-automation-id": "jobPostingTitleLink"})
    job = crawler._parse_one_html(
        link, "TestCo", "https://testco.wd5.myworkdayjobs.com/en-US/TestCo"
    )
    assert job["source_url"].startswith("https://testco.wd5.myworkdayjobs.com")
    assert "Senior-Data-Engineer_JR100001" in job["source_url"]


def test_parse_one_html_returns_none_for_empty_title():
    from bs4 import BeautifulSoup
    crawler = WorkdayCrawler(_BASE_CONFIG)
    soup = BeautifulSoup(
        '<a data-automation-id="jobPostingTitleLink" href="/job/x"></a>', "html.parser"
    )
    link = soup.find("a")
    assert crawler._parse_one_html(link, "TestCo", "https://testco.wd5.myworkdayjobs.com/en-US/TestCo") is None


def test_parse_one_html_returns_none_for_missing_href():
    from bs4 import BeautifulSoup
    crawler = WorkdayCrawler(_BASE_CONFIG)
    soup = BeautifulSoup(
        '<a data-automation-id="jobPostingTitleLink">Data Engineer</a>', "html.parser"
    )
    link = soup.find("a")
    assert crawler._parse_one_html(link, "TestCo", "https://testco.wd5.myworkdayjobs.com/en-US/TestCo") is None


def test_parse_one_html_source_url_preserved_when_href_is_absolute():
    from bs4 import BeautifulSoup
    crawler = WorkdayCrawler(_BASE_CONFIG)
    soup = BeautifulSoup(
        '<li><a data-automation-id="jobPostingTitleLink" '
        'href="https://testco.wd5.myworkdayjobs.com/en-US/TestCo/job/DE_JR001">Data Engineer</a></li>',
        "html.parser",
    )
    link = soup.find("a")
    job = crawler._parse_one_html(link, "TestCo", "https://testco.wd5.myworkdayjobs.com/en-US/TestCo")
    assert job is not None
    assert job["source_url"] == "https://testco.wd5.myworkdayjobs.com/en-US/TestCo/job/DE_JR001"


# ---------------------------------------------------------------------------
# parse() — unit tests (uses pre-built raw items, no HTTP)
# ---------------------------------------------------------------------------


def test_parse_raises_crawler_parse_error_for_non_list():
    with pytest.raises(CrawlerParseError):
        WorkdayCrawler(_BASE_CONFIG).parse({"not": "a list"})  # type: ignore


def test_parse_empty_list_returns_empty_list():
    assert WorkdayCrawler(_BASE_CONFIG).parse([]) == []


def test_parse_json_strategy_returns_job_dicts():
    fixture = _load_cxs_fixture()
    raw = [{
        "_strategy": "json",
        "_company_name": "TestCo",
        "_configured_url": "https://testco.wd5.myworkdayjobs.com/en-US/TestCo",
        "job_postings": fixture["jobPostings"],
    }]
    result = WorkdayCrawler(_BASE_CONFIG).parse(raw)
    assert len(result) == 2
    assert all(j["source_name"] == "workday" for j in result)
    assert all(j["company"] == "TestCo" for j in result)


def test_parse_html_strategy_returns_job_dicts():
    raw = [{
        "_strategy": "html",
        "_company_name": "TestCo",
        "_configured_url": "https://testco.wd5.myworkdayjobs.com/en-US/TestCo",
        "html": _load_html_fixture(),
    }]
    result = WorkdayCrawler(_BASE_CONFIG).parse(raw)
    assert len(result) == 2
    assert all(j["source_name"] == "workday" for j in result)


def test_parse_skips_item_with_unknown_strategy():
    raw = [{"_strategy": "ftp", "_company_name": "TestCo", "_configured_url": "x"}]
    result = WorkdayCrawler(_BASE_CONFIG).parse(raw)
    assert result == []


def test_parse_malformed_cxs_record_does_not_fail_batch():
    """One CXS record missing 'title' must not prevent valid records from being returned."""
    raw = [{
        "_strategy": "json",
        "_company_name": "TestCo",
        "_configured_url": "https://testco.wd5.myworkdayjobs.com/en-US/TestCo",
        "job_postings": [
            {"title": "Data Engineer", "externalPath": "/job/DE_JR001", "jobReqId": "JR001"},
            {"externalPath": "/job/NoTitle_JR002"},
            {"title": "Analytics Engineer", "externalPath": "/job/AE_JR003", "jobReqId": "JR003"},
        ],
    }]
    result = WorkdayCrawler(_BASE_CONFIG).parse(raw)
    assert len(result) == 2
    titles = {j["title"] for j in result}
    assert "Data Engineer" in titles
    assert "Analytics Engineer" in titles


def test_parse_returns_empty_when_html_has_no_job_links():
    """An HTML page with no job listings yields an empty result, not an error."""
    raw = [{
        "_strategy": "html",
        "_company_name": "TestCo",
        "_configured_url": "https://testco.wd5.myworkdayjobs.com/en-US/TestCo",
        "html": "<html><body><p>No jobs found.</p></body></html>",
    }]
    result = WorkdayCrawler(_BASE_CONFIG).parse(raw)
    assert result == []


def test_parse_empty_html_for_one_company_does_not_discard_other_results():
    """A company with no HTML job links must not discard results from other companies."""
    fixture = _load_cxs_fixture()
    raw = [
        {
            "_strategy": "json",
            "_company_name": "GoodCo",
            "_configured_url": "https://goodco.wd5.myworkdayjobs.com/en-US/GoodCo",
            "job_postings": fixture["jobPostings"],
        },
        {
            "_strategy": "html",
            "_company_name": "EmptyCo",
            "_configured_url": "https://emptyco.wd5.myworkdayjobs.com/en-US/EmptyCo",
            "html": "<html><body><p>No jobs.</p></body></html>",
        },
    ]
    result = WorkdayCrawler(_BASE_CONFIG).parse(raw)
    assert len(result) == 2
    assert all(j["company"] == "GoodCo" for j in result)


@patch("src.crawlers.workday.workday_http.post")
def test_fetch_cxs_stops_when_page_returns_empty_job_list(mock_post):
    """Pagination stops when API returns empty jobPostings before offset reaches total."""
    page1 = {
        "jobPostings": [{"title": "Job 0", "externalPath": "/job/J0", "jobReqId": "JR0"}],
        "total": 100,
    }
    page2 = {"jobPostings": [], "total": 100}
    mock_post.side_effect = [_mock_post_response(page1), _mock_post_response(page2)]
    crawler = WorkdayCrawler(_BASE_CONFIG)
    jobs = crawler._fetch_cxs(
        "https://testco.wd5.myworkdayjobs.com/wday/cxs/testco/TestCo/jobs"
    )
    assert mock_post.call_count == 2
    assert len(jobs) == 1


# ---------------------------------------------------------------------------
# fetch() — tests (HTTP and Playwright mocked)
# ---------------------------------------------------------------------------


@patch("src.crawlers.workday.workday_http.post")
def test_fetch_returns_json_strategy_item_on_cxs_success(mock_post):
    mock_post.return_value = _mock_post_response(_load_cxs_fixture())
    result = WorkdayCrawler(_BASE_CONFIG).fetch()
    assert len(result) == 1
    assert result[0]["_strategy"] == "json"
    assert result[0]["_company_name"] == "TestCo"
    assert len(result[0]["job_postings"]) == 2


@patch("src.crawlers.workday.playwright_utils.render_page")
@patch("src.crawlers.workday.workday_http.post")
def test_fetch_falls_back_to_playwright_when_cxs_fails(mock_post, mock_render):
    mock_post.side_effect = CrawlerFetchError("403 Forbidden")
    mock_render.return_value = _load_html_fixture()
    result = WorkdayCrawler(_BASE_CONFIG).fetch()
    assert len(result) == 1
    assert result[0]["_strategy"] == "html"
    mock_render.assert_called_once()


@patch("src.crawlers.workday.playwright_utils.render_page")
@patch("src.crawlers.workday.workday_http.post")
def test_fetch_skips_url_when_both_strategies_fail(mock_post, mock_render):
    mock_post.side_effect = CrawlerFetchError("403")
    mock_render.side_effect = CrawlerFetchError("timeout")
    result = WorkdayCrawler(_BASE_CONFIG).fetch()
    assert result == []


@patch("src.crawlers.workday.workday_http.post")
def test_fetch_returns_empty_list_when_no_urls_configured(mock_post):
    result = WorkdayCrawler({"workday_urls": {}}).fetch()
    assert result == []
    mock_post.assert_not_called()


@patch("src.crawlers.workday.workday_http.post")
def test_fetch_skips_invalid_url(mock_post):
    config = {**_BASE_CONFIG, "workday_urls": {"BadCo": "https://not-workday.com/jobs"}}
    result = WorkdayCrawler(config).fetch()
    assert result == []
    mock_post.assert_not_called()


@patch("src.crawlers.workday.workday_http.post")
def test_fetch_one_failed_url_does_not_stop_others(mock_post):
    """A CXS + Playwright failure for the first company must not stop the second."""
    good_fixture = _load_cxs_fixture()

    def _side_effect(url, **kwargs):
        if "testco" in url:
            raise CrawlerFetchError("403")
        return _mock_post_response(good_fixture)

    config = {
        **_BASE_CONFIG,
        "workday_urls": {
            "TestCo": "https://testco.wd5.myworkdayjobs.com/en-US/TestCo",
            "GoodCo": "https://goodco.wd5.myworkdayjobs.com/en-US/GoodCo",
        },
    }
    with patch(
        "src.crawlers.workday.playwright_utils.render_page",
        side_effect=CrawlerFetchError("pw fail"),
    ) as mock_render:
        mock_post.side_effect = _side_effect
        result = WorkdayCrawler(config).fetch()

    mock_render.assert_called_once()
    assert len(result) == 1
    assert result[0]["_company_name"] == "GoodCo"


@patch("src.crawlers.workday.workday_http.post")
def test_fetch_paginates_when_total_exceeds_limit(mock_post):
    """When total > 20 fetch must POST additional pages with incremented offset."""
    page1 = {
        "jobPostings": [
            {"title": f"Job {i}", "externalPath": f"/job/J{i}", "jobReqId": f"JR{i}"}
            for i in range(20)
        ],
        "total": 25,
    }
    page2 = {
        "jobPostings": [
            {"title": f"Job {i}", "externalPath": f"/job/J{i}", "jobReqId": f"JR{i}"}
            for i in range(20, 25)
        ],
        "total": 25,
    }
    mock_post.side_effect = [_mock_post_response(page1), _mock_post_response(page2)]
    result = WorkdayCrawler(_BASE_CONFIG).fetch()
    assert mock_post.call_count == 2
    assert len(result[0]["job_postings"]) == 25


@patch("src.crawlers.workday.workday_http.post")
def test_fetch_pagination_resilience_partial_results_preserved(mock_post):
    """If page 1 succeeds and page 2 fails, jobs from page 1 must still be returned."""
    page1 = {
        "jobPostings": [
            {"title": f"Job {i}", "externalPath": f"/job/J{i}", "jobReqId": f"JR{i}"}
            for i in range(20)
        ],
        "total": 25,
    }
    mock_post.side_effect = [
        _mock_post_response(page1),
        CrawlerFetchError("500 on page 2"),
    ]
    result = WorkdayCrawler(_BASE_CONFIG).fetch()
    assert len(result) == 1
    assert result[0]["_strategy"] == "json"
    assert len(result[0]["job_postings"]) == 20


@patch("src.crawlers.workday.workday_http.post")
def test_fetch_cxs_raises_when_job_postings_key_missing(mock_post):
    mock_post.return_value = _mock_post_response({"error": "not found"})
    with pytest.raises(CrawlerFetchError, match="jobPostings"):
        WorkdayCrawler(_BASE_CONFIG)._fetch_cxs(
            "https://testco.wd5.myworkdayjobs.com/wday/cxs/testco/TestCo/jobs"
        )


# ---------------------------------------------------------------------------
# run() — integration tests
# ---------------------------------------------------------------------------


@patch("src.crawlers.workday.workday_http.post")
def test_run_returns_job_dicts_from_cxs_fixture(mock_post):
    mock_post.return_value = _mock_post_response(_load_cxs_fixture())
    result = WorkdayCrawler(_BASE_CONFIG).run()
    assert len(result) == 2
    for job in result:
        assert "title" in job
        assert "company" in job
        assert "source_url" in job
        assert job["source_name"] == "workday"
        assert job["company"] == "TestCo"


@patch("src.crawlers.workday.playwright_utils.render_page")
@patch("src.crawlers.workday.workday_http.post")
def test_run_falls_back_to_playwright_on_cxs_failure(mock_post, mock_render):
    mock_post.side_effect = CrawlerFetchError("403")
    mock_render.return_value = _load_html_fixture()
    result = WorkdayCrawler(_BASE_CONFIG).run()
    assert len(result) == 2
    assert all(j["source_name"] == "workday" for j in result)
    assert all(j["company"] == "TestCo" for j in result)


@patch("src.crawlers.workday.playwright_utils.render_page")
@patch("src.crawlers.workday.workday_http.post")
def test_run_returns_empty_list_when_all_urls_fail(mock_post, mock_render):
    mock_post.side_effect = CrawlerFetchError("403")
    mock_render.side_effect = CrawlerFetchError("timeout")
    result = WorkdayCrawler(_BASE_CONFIG).run()
    assert result == []


@patch("src.crawlers.workday.workday_http.post")
def test_run_source_name_is_workday_for_all_jobs(mock_post):
    mock_post.return_value = _mock_post_response(_load_cxs_fixture())
    result = WorkdayCrawler(_BASE_CONFIG).run()
    assert len(result) > 0
    assert all(j["source_name"] == "workday" for j in result)
