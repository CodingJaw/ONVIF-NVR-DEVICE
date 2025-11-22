import unittest

from fastapi import HTTPException

from src.security import create_username_token, verify_wsse
from src.users import AuthenticatedUser


class _DummyStore:
    def __init__(self, username: str = "alice", password: str = "secret", roles: list[str] | None = None):
        self.username = username
        self.password = password
        self.roles = roles or ["viewer"]

    def authenticate(self, username: str, password: str):
        if username == self.username and password == self.password:
            return AuthenticatedUser(username=username, roles=self.roles)
        raise ValueError("Invalid credentials")


class VerifyWsseLoggingTestCase(unittest.TestCase):
    def test_success_logs_parsed_token(self) -> None:
        store = _DummyStore()
        token = 'UsernameToken username="alice" password="secret"'

        with self.assertLogs("src.security", level="DEBUG") as logs:
            user = verify_wsse(username_token=token, store=store)

        self.assertIsInstance(user, AuthenticatedUser)
        parsed_logs = [record for record in logs.records if record.getMessage() == "Parsed UsernameToken"]
        self.assertTrue(parsed_logs, "Expected parsed token log entry")
        self.assertEqual(parsed_logs[0].username, "alice")
        self.assertEqual(parsed_logs[0].password_masked, "******")

    def test_create_username_token_from_clear_credentials(self) -> None:
        token = create_username_token("bob", "hunter2")

        self.assertEqual(token, 'UsernameToken username="bob" password="hunter2"')

        store = _DummyStore(username="bob", password="hunter2")
        user = verify_wsse(username_token=token, store=store)

        self.assertEqual(user.username, "bob")

    def test_missing_header_logs_failure_reason(self) -> None:
        store = _DummyStore()

        with self.assertLogs("src.security", level="DEBUG") as logs:
            with self.assertRaises(HTTPException) as ctx:
                verify_wsse(username_token=None, store=store)

        self.assertEqual(ctx.exception.status_code, 401)
        reasons = [record.reason for record in logs.records if hasattr(record, "reason")]
        self.assertIn("missing_username_token", reasons)

    def test_malformed_and_invalid_credentials_log_failure_reason(self) -> None:
        store = _DummyStore()

        with self.assertLogs("src.security", level="DEBUG") as malformed_logs:
            with self.assertRaises(HTTPException) as malformed_ctx:
                verify_wsse(username_token="not-a-token", store=store)

        self.assertEqual(malformed_ctx.exception.status_code, 403)
        malformed_reasons = [record.reason for record in malformed_logs.records if hasattr(record, "reason")]
        self.assertIn("Malformed UsernameToken header", malformed_reasons)

        with self.assertLogs("src.security", level="DEBUG") as invalid_logs:
            with self.assertRaises(HTTPException) as invalid_ctx:
                verify_wsse(username_token='UsernameToken username="alice" password="wrong"', store=store)

        self.assertEqual(invalid_ctx.exception.status_code, 403)
        invalid_reasons = [record.reason for record in invalid_logs.records if hasattr(record, "reason")]
        self.assertIn("Invalid credentials", invalid_reasons)


if __name__ == "__main__":
    unittest.main()
