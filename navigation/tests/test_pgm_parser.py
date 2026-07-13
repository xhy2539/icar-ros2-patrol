"""Unit tests for parse_pgm — P2 (ASCII) and P5 (binary) PGM parsing."""

import os
import struct
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from navigation_utils import parse_pgm


def _write_pgm(path: Path, content: bytes):
    path.write_bytes(content)


class P2AsciiTest(unittest.TestCase):
    """Tests for P2 (ASCII) PGM format — our mock map convention."""

    def test_parse_mock_lab_map(self):
        w, h, occ = parse_pgm(
            Path(__file__).resolve().parents[2]
            / "config" / "navigation" / "maps" / "mock_lab.pgm"
        )
        self.assertEqual(w, 12)
        self.assertEqual(h, 12)
        self.assertEqual(len(occ), 144)
        # Top and bottom borders are walls
        self.assertEqual(occ[0:12], [100] * 12)
        self.assertEqual(occ[132:144], [100] * 12)
        # Row 3: two wall blocks in the middle
        self.assertEqual(
            occ[36:48],
            [100, 0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 100],
        )

    def test_small_p2_no_invert(self):
        # 2 cols × 3 rows, max=100
        # Row-major: row0=[0,50], row1=[100,25], row2=[75,90]
        pgm = b"P2\n2 3\n100\n  0  50 100\n 25  75  90\n"
        with tempfile.NamedTemporaryFile(suffix=".pgm", delete=False) as f:
            f.write(pgm)
            tmp = f.name
        try:
            w, h, occ = parse_pgm(Path(tmp), invert=False)
            self.assertEqual(w, 2)
            self.assertEqual(h, 3)
            # 0/100=0.0 → free(0),  50/100=0.5 → unknown(-1)
            # 100/100=1.0 → occ(100), 25/100=0.25 → unknown(-1)
            # 75/100=0.75 → occ(100), 90/100=0.9 → occ(100)
            self.assertEqual(occ, [0, -1, 100, -1, 100, 100])
        finally:
            os.unlink(tmp)

    def test_comment_lines_are_skipped(self):
        pgm = (
            b"P2\n"
            b"# This is a comment\n"
            b"2 2\n"
            b"# Another comment\n"
            b"100\n"
            b"0 100\n"
            b"50 0\n"
        )
        with tempfile.NamedTemporaryFile(suffix=".pgm", delete=False) as f:
            f.write(pgm)
            tmp = f.name
        try:
            w, h, occ = parse_pgm(Path(tmp), invert=False)
            self.assertEqual(w, 2)
            self.assertEqual(h, 2)
            self.assertEqual(len(occ), 4)
        finally:
            os.unlink(tmp)


class P5BinaryTest(unittest.TestCase):
    """Tests for P5 (binary) PGM format — standard ROS SLAM output."""

    def test_small_p5_no_invert(self):
        # 3x3: white border (255), black center (0)
        data = bytes([255, 255, 255, 255, 0, 255, 255, 255, 255])
        pgm = b"P5\n3 3\n255\n" + data
        with tempfile.NamedTemporaryFile(suffix=".pgm", delete=False) as f:
            f.write(pgm)
            tmp = f.name
        try:
            w, h, occ = parse_pgm(Path(tmp), invert=False)
            self.assertEqual(w, 3)
            self.assertEqual(h, 3)
            # Without invert: 255=occupied(100), 0=free(0)
            self.assertEqual(occ[0], 100)   # border → occupied
            self.assertEqual(occ[4], 0)     # center → free
        finally:
            os.unlink(tmp)

    def test_p5_with_invert_standard_ros_convention(self):
        # Standard ROS SLAM output: 0=black=obstacle, 254=white=free
        data = bytes([0, 254, 254, 0])
        pgm = b"P5\n2 2\n254\n" + data
        with tempfile.NamedTemporaryFile(suffix=".pgm", delete=False) as f:
            f.write(pgm)
            tmp = f.name
        try:
            w, h, occ = parse_pgm(Path(tmp), invert=True)
            self.assertEqual(w, 2)
            self.assertEqual(h, 2)
            # 0/254=0.0 ≤ 0.35 → occupied(100)
            # 254/254=1.0 ≥ 0.80 → free(0)
            self.assertEqual(occ, [100, 0, 0, 100])
        finally:
            os.unlink(tmp)

    def test_p5_16bit_with_invert(self):
        # 16-bit P5: max_value > 255
        data = struct.pack(">HHHH", 0, 65535, 32767, 16384)
        pgm = b"P5\n2 2\n65535\n" + data
        with tempfile.NamedTemporaryFile(suffix=".pgm", delete=False) as f:
            f.write(pgm)
            tmp = f.name
        try:
            w, h, occ = parse_pgm(Path(tmp), invert=True)
            self.assertEqual(w, 2)
            self.assertEqual(h, 2)
            # 0/65535=0.0 → occupied(100)
            # 65535/65535=1.0 → free(0)
            # 32767/65535≈0.5 → unknown(-1)
            # 16384/65535≈0.25 → occupied(100)
            self.assertEqual(occ, [100, 0, -1, 100])
        finally:
            os.unlink(tmp)

    def test_p5_with_comment_lines(self):
        pgm = (
            b"P5\n"
            b"# Creator: gmapping\n"
            b"2 2\n"
            b"# Max value\n"
            b"255\n"
            + bytes([0, 128, 200, 255])
        )
        with tempfile.NamedTemporaryFile(suffix=".pgm", delete=False) as f:
            f.write(pgm)
            tmp = f.name
        try:
            w, h, occ = parse_pgm(Path(tmp), invert=True)
            self.assertEqual(w, 2)
            self.assertEqual(h, 2)
            self.assertEqual(len(occ), 4)
        finally:
            os.unlink(tmp)


class ErrorHandlingTest(unittest.TestCase):
    """Tests for parse error handling."""

    def test_unsupported_magic_number(self):
        pgm = b"P3\n2 2\n255\n0 128 200 255 0 128 200 255 0 128 200 255\n"
        with tempfile.NamedTemporaryFile(suffix=".pgm", delete=False) as f:
            f.write(pgm)
            tmp = f.name
        try:
            with self.assertRaises(ValueError, msg="Should reject P3/PPM"):
                parse_pgm(Path(tmp))
        finally:
            os.unlink(tmp)

    def test_size_mismatch_detected(self):
        data = bytes([0, 0, 0])  # only 3 bytes for a 2x2=4 image
        pgm = b"P5\n2 2\n255\n" + data
        with tempfile.NamedTemporaryFile(suffix=".pgm", delete=False) as f:
            f.write(pgm)
            tmp = f.name
        try:
            with self.assertRaises(ValueError, msg="Should detect size mismatch"):
                parse_pgm(Path(tmp))
        finally:
            os.unlink(tmp)


if __name__ == "__main__":
    unittest.main()
