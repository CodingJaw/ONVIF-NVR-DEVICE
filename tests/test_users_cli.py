import io
import contextlib
import unittest

from src import users


class UsersCliTestCase(unittest.TestCase):
    def test_list_subcommand_runs_without_type_error(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = users.main(["list"])
        self.assertEqual(exit_code, 0)
        self.assertTrue(stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
