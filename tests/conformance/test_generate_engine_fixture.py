import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from generate_engine_fixture import _timestamp  # noqa: E402


class TimestampConversionTest(unittest.TestCase):
    def test_epoch(self):
        self.assertEqual(_timestamp("1970-01-01T00:00:00Z"), "0")

    def test_one_second_after_epoch(self):
        self.assertEqual(_timestamp("1970-01-01T00:00:01Z"), "1000000000")

    def test_one_microsecond_after_epoch(self):
        self.assertEqual(_timestamp("1970-01-01T00:00:00.000001Z"), "1000")

    def test_before_epoch(self):
        self.assertEqual(_timestamp("1969-12-31T23:59:59.999999999Z"), "-1")

    def test_timezone_offsets_are_normalized(self):
        expected = _timestamp("2026-01-05T09:00:00Z")
        self.assertEqual(_timestamp("2026-01-05T10:00:00+01:00"), expected)
        self.assertEqual(_timestamp("2026-01-05T04:00:00-05:00"), expected)

    def test_current_fixture_timestamp(self):
        self.assertEqual(
            _timestamp("2026-01-05T09:00:00Z"), "1767603600000000000"
        )

    def test_nanosecond_precision(self):
        self.assertEqual(_timestamp("1970-01-01T00:00:00.123456789Z"), "123456789")
        self.assertEqual(_timestamp("1970-01-01T00:00:00.123400000Z"), "123400000")

    def test_more_than_nanosecond_precision_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "precision exceeds nanoseconds"):
            _timestamp("1970-01-01T00:00:00.1234567890Z")


if __name__ == "__main__":
    unittest.main()
