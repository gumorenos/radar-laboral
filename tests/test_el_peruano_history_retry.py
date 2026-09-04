from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import Mock, patch

import requests

from radar_laboral.collectors.el_peruano_history import _fetch_day_with_retry
from radar_laboral.collectors.el_peruano_search import SearchCollectorError


class HistoricalFetchRetryTests(unittest.TestCase):
    def test_transient_http_error_then_success(self) -> None:
        response = Mock(status_code=404)
        error = requests.HTTPError("temporary 404", response=response)
        expected = [{"id": "elperuano:1-1"}]
        session = Mock()

        with patch(
            "radar_laboral.collectors.el_peruano_history.fetch_day",
            side_effect=[error, expected],
        ) as fetch_mock, patch(
            "radar_laboral.collectors.el_peruano_history.time.sleep"
        ) as sleep_mock:
            result = _fetch_day_with_retry(
                session, date(2025, 9, 24), page_delay_seconds=0,
                attempts=4, retry_backoff_seconds=1,
            )

        self.assertEqual(result, expected)
        self.assertEqual(fetch_mock.call_count, 2)
        session.close.assert_called_once_with()
        sleep_mock.assert_called_once_with(1)

    def test_rate_limit_and_server_error_then_success(self) -> None:
        errors = [
            requests.HTTPError("429"),
            requests.HTTPError("503"),
        ]
        session = Mock()
        with patch(
            "radar_laboral.collectors.el_peruano_history.fetch_day",
            side_effect=[*errors, []],
        ), patch(
            "radar_laboral.collectors.el_peruano_history.time.sleep"
        ) as sleep_mock:
            result = _fetch_day_with_retry(
                session, date(2025, 9, 24), page_delay_seconds=0,
                attempts=4, retry_backoff_seconds=1,
            )

        self.assertEqual(result, [])
        self.assertEqual(session.close.call_count, 2)
        self.assertEqual([call.args[0] for call in sleep_mock.call_args_list], [1, 2])

    def test_ssl_eof_resets_connection_pool_before_retry(self) -> None:
        session = Mock()
        error = requests.exceptions.SSLError("UNEXPECTED_EOF_WHILE_READING")
        expected = [{"id": "elperuano:ssl-recovered"}]

        with patch(
            "radar_laboral.collectors.el_peruano_history.fetch_day",
            side_effect=[error, expected],
        ) as fetch_mock, patch(
            "radar_laboral.collectors.el_peruano_history.time.sleep"
        ) as sleep_mock:
            result = _fetch_day_with_retry(
                session,
                date(2025, 11, 1),
                page_delay_seconds=0,
                attempts=6,
                retry_backoff_seconds=1,
            )

        self.assertEqual(result, expected)
        self.assertEqual(fetch_mock.call_count, 2)
        session.close.assert_called_once_with()
        sleep_mock.assert_called_once_with(1)

    def test_retry_delay_is_capped_for_long_outages(self) -> None:
        session = Mock()
        error = requests.ConnectionError("temporary outage")

        with patch(
            "radar_laboral.collectors.el_peruano_history.fetch_day",
            side_effect=[error, error, error, error, error, []],
        ), patch(
            "radar_laboral.collectors.el_peruano_history.time.sleep"
        ) as sleep_mock:
            result = _fetch_day_with_retry(
                session,
                date(2025, 11, 1),
                page_delay_seconds=0,
                attempts=6,
                retry_backoff_seconds=1,
                max_retry_delay_seconds=15,
            )

        self.assertEqual(result, [])
        self.assertEqual(session.close.call_count, 5)
        self.assertEqual(
            [call.args[0] for call in sleep_mock.call_args_list],
            [1, 2, 4, 8, 15],
        )

    def test_collector_integrity_error_is_retried_without_resetting_session(self) -> None:
        session = Mock()
        with patch(
            "radar_laboral.collectors.el_peruano_history.fetch_day",
            side_effect=[SearchCollectorError("malformed source response"), []],
        ) as fetch_mock, patch(
            "radar_laboral.collectors.el_peruano_history.time.sleep"
        ):
            result = _fetch_day_with_retry(
                session, date(2025, 9, 24), page_delay_seconds=0,
                attempts=2, retry_backoff_seconds=0,
            )

        self.assertEqual(result, [])
        self.assertEqual(fetch_mock.call_count, 2)
        session.close.assert_not_called()

    def test_exhausted_retries_propagate_source_error(self) -> None:
        error = requests.HTTPError("persistent 404")
        session = Mock()
        with patch(
            "radar_laboral.collectors.el_peruano_history.fetch_day",
            side_effect=error,
        ) as fetch_mock, patch(
            "radar_laboral.collectors.el_peruano_history.time.sleep"
        ) as sleep_mock:
            with self.assertRaises(requests.HTTPError):
                _fetch_day_with_retry(
                    session, date(2025, 9, 24), page_delay_seconds=0,
                    attempts=4, retry_backoff_seconds=1,
                )

        self.assertEqual(fetch_mock.call_count, 4)
        self.assertEqual(session.close.call_count, 4)
        self.assertEqual([call.args[0] for call in sleep_mock.call_args_list], [1, 2, 4])

    def test_programming_errors_are_not_retried(self) -> None:
        session = Mock()
        with patch(
            "radar_laboral.collectors.el_peruano_history.fetch_day",
            side_effect=ValueError("bug"),
        ) as fetch_mock, patch(
            "radar_laboral.collectors.el_peruano_history.time.sleep"
        ) as sleep_mock:
            with self.assertRaises(ValueError):
                _fetch_day_with_retry(
                    session, date(2025, 9, 24), page_delay_seconds=0,
                    attempts=4, retry_backoff_seconds=1,
                )

        fetch_mock.assert_called_once()
        session.close.assert_not_called()
        sleep_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
