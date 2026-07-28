"""
Tests for logging configuration, including file rotation.
"""

import logging
import os

import pytest

from app.logging_config import setup_logging


# Fixture: clean root logger before and after each test
@pytest.fixture(autouse=True)
def clean_root_logger():
    """Remove all handlers from root logger before and after test."""
    root = logging.getLogger()
    before = root.handlers[:]
    root.handlers.clear()
    yield
    root.handlers.clear()


class TestSetupLoggingRotation:
    def test_no_rotation_uses_file_handler(self, tmp_path):
        """When rotation is not specified, use plain FileHandler."""
        log_file = tmp_path / "test.log"
        config = {
            "logging": {
                "level": "DEBUG",
                "file": str(log_file),
            }
        }
        setup_logging(config)
        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1
        assert not isinstance(file_handlers[0], logging.handlers.RotatingFileHandler)
        assert not isinstance(file_handlers[0], logging.handlers.TimedRotatingFileHandler)

    def test_rotation_null_uses_file_handler(self, tmp_path):
        """When rotation is null, use plain FileHandler."""
        log_file = tmp_path / "test.log"
        config = {
            "logging": {
                "level": "DEBUG",
                "file": str(log_file),
                "rotation": None,
            }
        }
        setup_logging(config)
        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1
        assert not isinstance(file_handlers[0], logging.handlers.RotatingFileHandler)

    def test_rotation_type_size(self, tmp_path):
        """rotation.type=size creates RotatingFileHandler."""
        log_file = tmp_path / "test.log"
        config = {
            "logging": {
                "level": "DEBUG",
                "file": str(log_file),
                "rotation": {
                    "type": "size",
                    "max_bytes": 1024,
                    "backup_count": 3,
                },
            }
        }
        setup_logging(config)
        root = logging.getLogger()
        rotating = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert len(rotating) == 1
        handler = rotating[0]
        assert handler.maxBytes == 1024
        assert handler.backupCount == 3

    def test_rotation_type_timed(self, tmp_path):
        """rotation.type=timed creates TimedRotatingFileHandler."""
        log_file = tmp_path / "test.log"
        config = {
            "logging": {
                "level": "DEBUG",
                "file": str(log_file),
                "rotation": {
                    "type": "timed",
                    "when": "midnight",
                    "interval": 1,
                    "backup_count": 14,
                },
            }
        }
        setup_logging(config)
        root = logging.getLogger()
        timed = [h for h in root.handlers if isinstance(h, logging.handlers.TimedRotatingFileHandler)]
        assert len(timed) == 1
        handler = timed[0]
        assert handler.when == "MIDNIGHT"
        assert handler.backupCount == 14

    def test_rotation_unknown_type_falls_back(self, tmp_path):
        """Unknown rotation.type falls back to plain FileHandler."""
        log_file = tmp_path / "test.log"
        config = {
            "logging": {
                "level": "DEBUG",
                "file": str(log_file),
                "rotation": {
                    "type": "unknown_type",
                },
            }
        }
        setup_logging(config)
        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        # Should have a FileHandler, but not RotatingFileHandler or TimedRotatingFileHandler
        has_plain = any(
            not isinstance(h, logging.handlers.RotatingFileHandler) and
            not isinstance(h, logging.handlers.TimedRotatingFileHandler)
            for h in file_handlers
        )
        assert has_plain

    def test_rotation_file_io_error(self, capsys):
        """IOError when creating rotating handler is caught and logged."""
        config = {
            "logging": {
                "level": "DEBUG",
                "file": "/nonexistent_dir_xyz/logs/app.log",
                "rotation": {
                    "type": "size",
                    "max_bytes": 1024,
                    "backup_count": 3,
                },
            }
        }
        setup_logging(config)
        captured = capsys.readouterr()
        assert "Failed to set up log file" in captured.out
