"""Shared pytest configuration and helpers for poly-lithic tests."""

import random
import time
import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "flaky_p4p(retries=3, backoff_max=2.0): "
        "retry p4p/network tests with random backoff",
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Retry tests marked with @pytest.mark.flaky_p4p on call-phase failure."""
    outcome = yield
    report = outcome.get_result()

    if report.when != "call" or not report.failed:
        return

    marker = item.get_closest_marker("flaky_p4p")
    if marker is None:
        return

    retries = marker.kwargs.get("retries", 3)
    backoff_max = marker.kwargs.get("backoff_max", 2.0)

    for attempt in range(2, retries + 1):
        wait = random.uniform(0.1, backoff_max * attempt)
        terminal = item.config.pluginmanager.get_plugin("terminalreporter")
        if terminal is not None:
            terminal.write_line(
                f"  \u21bb {item.nodeid} failed (attempt {attempt - 1}/{retries}), "
                f"retrying in {wait:.2f}s \u2026",
                yellow=True,
            )
        time.sleep(wait)

        # Re-run the test's setup and call phases
        item.setup()
        try:
            item.runtest()
        except Exception:
            continue  # still failing, try again

        # Passed on retry — override the report to mark it as passed
        report.outcome = "passed"
        report.longrepr = None
        report.wasxfail = None
        return

    # All retries exhausted — leave the original failure report as-is
