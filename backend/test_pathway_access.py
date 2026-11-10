
import os
import unittest

from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

from pathway_access import require_pathway_dev_access


class TestPathwayAccess(unittest.TestCase):

    def setUp(self):

        # Test-only key. Never use this as a real secret.
        self.test_key = "test-only-" + ("A" * 40)

    def make_request(
        self,
        host="127.0.0.1",
        supplied_key=None
    ):
        """
        Construct a simulated HTTP request.

        No server is started and no real network
        connection is made.
        """

        headers = []

        if supplied_key is not None:
            headers.append((
                b"x-futurepath-dev-key",
                supplied_key.encode("utf-8")
            ))

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/pathways",
            "headers": headers,
            "client": (
                (host, 54000)
                if host is not None
                else None
            )
        }

        return Request(scope)

    # --------------------------------------------------
    # 1. Access disabled without configuration
    # --------------------------------------------------

    def test_access_disabled_without_configured_key(self):

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": ""}
        ):

            request = self.make_request(
                supplied_key="any-key"
            )

            with self.assertRaises(
                HTTPException
            ) as captured:

                require_pathway_dev_access(request)

        self.assertEqual(
            captured.exception.status_code,
            503
        )

    # --------------------------------------------------
    # 2. Short configuration keys are rejected
    # --------------------------------------------------

    def test_short_configured_key_is_rejected(self):

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": "short-key"}
        ):

            request = self.make_request(
                supplied_key="short-key"
            )

            with self.assertRaises(
                HTTPException
            ) as captured:

                require_pathway_dev_access(request)

        self.assertEqual(
            captured.exception.status_code,
            503
        )

    # --------------------------------------------------
    # 3. Non-local clients are rejected
    # --------------------------------------------------

    def test_remote_client_is_rejected(self):

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": self.test_key}
        ):

            # Even the correct key must not permit
            # non-local access.
            for host in [
                "192.168.1.100",
                "203.0.113.10",
                "testclient",
                "localhost"
            ]:

                with self.subTest(host=host):

                    request = self.make_request(
                        host=host,
                        supplied_key=self.test_key
                    )

                    with self.assertRaises(
                        HTTPException
                    ) as captured:

                        require_pathway_dev_access(request)

                    self.assertEqual(
                        captured.exception.status_code,
                        403
                    )

    # --------------------------------------------------
    # 4. Missing client information is rejected
    # --------------------------------------------------

    def test_missing_client_information_is_rejected(self):

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": self.test_key}
        ):

            request = self.make_request(
                host=None,
                supplied_key=self.test_key
            )

            with self.assertRaises(
                HTTPException
            ) as captured:

                require_pathway_dev_access(request)

        self.assertEqual(
            captured.exception.status_code,
            403
        )

    # --------------------------------------------------
    # 5. Missing request key is rejected
    # --------------------------------------------------

    def test_missing_request_key_is_rejected(self):

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": self.test_key}
        ):

            request = self.make_request(
                host="127.0.0.1",
                supplied_key=None
            )

            with self.assertRaises(
                HTTPException
            ) as captured:

                require_pathway_dev_access(request)

        self.assertEqual(
            captured.exception.status_code,
            401
        )

    # --------------------------------------------------
    # 6. Incorrect request key is rejected
    # --------------------------------------------------

    def test_incorrect_request_key_is_rejected(self):

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": self.test_key}
        ):

            request = self.make_request(
                host="127.0.0.1",
                supplied_key="incorrect-key"
            )

            with self.assertRaises(
                HTTPException
            ) as captured:

                require_pathway_dev_access(request)

        self.assertEqual(
            captured.exception.status_code,
            401
        )

    # --------------------------------------------------
    # 7. Correct key and IPv4 loopback are accepted
    # --------------------------------------------------

    def test_valid_ipv4_local_access(self):

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": self.test_key}
        ):

            request = self.make_request(
                host="127.0.0.1",
                supplied_key=self.test_key
            )

            result = require_pathway_dev_access(
                request
            )

        self.assertIsNone(result)

    # --------------------------------------------------
    # 8. Correct key and IPv6 loopback are accepted
    # --------------------------------------------------

    def test_valid_ipv6_local_access(self):

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": self.test_key}
        ):

            request = self.make_request(
                host="::1",
                supplied_key=self.test_key
            )

            result = require_pathway_dev_access(
                request
            )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
