"""
Live log tailing command for Django.

Usage:
    python manage.py taillog                    # All logs
    python manage.py taillog debug              # Debug log only
    python manage.py taillog orders delivery    # Multiple logs
    python manage.py taillog --filter ERROR     # Filter by level
    python manage.py taillog -n 50              # Show last 50 lines first

Available logs: debug, error, orders, delivery, api, security
"""

import os
import sys
import time
import re
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings


class Colors:
    """ANSI color codes for terminal output."""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'

    # Log levels
    DEBUG = '\033[36m'      # Cyan
    INFO = '\033[32m'       # Green
    WARNING = '\033[33m'    # Yellow
    ERROR = '\033[31m'      # Red
    CRITICAL = '\033[35m'   # Magenta

    # Components
    TIMESTAMP = '\033[90m'  # Gray
    FILENAME = '\033[34m'   # Blue
    LINE = '\033[90m'       # Gray


class LogTailer:
    """Tails multiple log files with live updates."""

    LOG_FILES = {
        'debug': 'debug.log',
        'error': 'error.log',
        'orders': 'orders.log',
        'delivery': 'delivery.log',
        'api': 'api.log',
        'security': 'security.log',
    }

    LEVEL_COLORS = {
        'DEBUG': Colors.DEBUG,
        'INFO': Colors.INFO,
        'WARNING': Colors.WARNING,
        'ERROR': Colors.ERROR,
        'CRITICAL': Colors.CRITICAL,
    }

    # Pattern to match log format: [LEVEL] TIMESTAMP NAME MODULE.FUNC:LINE - MESSAGE
    LOG_PATTERN = re.compile(
        r'\[(?P<level>\w+)\]\s+'
        r'(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+'
        r'(?P<name>[\w.]+)\s+'
        r'(?P<location>[\w.]+:\d+)\s+-\s+'
        r'(?P<message>.*)'
    )

    def __init__(self, logs_dir, log_names=None, level_filter=None, colorize=True):
        self.logs_dir = Path(logs_dir)
        self.log_names = log_names or list(self.LOG_FILES.keys())
        self.level_filter = level_filter.upper() if level_filter else None
        self.colorize = colorize and sys.stdout.isatty()
        self.file_positions = {}

    def get_log_path(self, name):
        """Get full path for a log file."""
        filename = self.LOG_FILES.get(name)
        if filename:
            return self.logs_dir / filename
        return None

    def colorize_line(self, line):
        """Add color codes to log line."""
        if not self.colorize:
            return line

        match = self.LOG_PATTERN.match(line)
        if match:
            level = match.group('level')
            timestamp = match.group('timestamp')
            name = match.group('name')
            location = match.group('location')
            message = match.group('message')

            level_color = self.LEVEL_COLORS.get(level, Colors.RESET)

            return (
                f"{Colors.TIMESTAMP}[{Colors.RESET}"
                f"{level_color}{Colors.BOLD}{level}{Colors.RESET}"
                f"{Colors.TIMESTAMP}]{Colors.RESET} "
                f"{Colors.TIMESTAMP}{timestamp}{Colors.RESET} "
                f"{Colors.FILENAME}{name}{Colors.RESET} "
                f"{Colors.LINE}{location}{Colors.RESET} - "
                f"{level_color}{message}{Colors.RESET}"
            )
        return line

    def should_show_line(self, line):
        """Check if line matches level filter."""
        if not self.level_filter:
            return True

        match = self.LOG_PATTERN.match(line)
        if match:
            level = match.group('level')
            level_order = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

            try:
                filter_idx = level_order.index(self.level_filter)
                line_idx = level_order.index(level)
                return line_idx >= filter_idx
            except ValueError:
                return True
        return True

    def get_last_lines(self, filepath, n=20):
        """Get last n lines of a file."""
        if not filepath.exists():
            return []

        try:
            with open(filepath, 'rb') as f:
                # Seek to end
                f.seek(0, 2)
                file_size = f.tell()

                # Read backwards to find n lines
                block_size = 8192
                blocks = []
                remaining = file_size

                while remaining > 0 and len(blocks) * block_size < file_size:
                    block_num = min(block_size, remaining)
                    remaining -= block_num
                    f.seek(remaining)
                    blocks.insert(0, f.read(block_num))

                    # Check if we have enough lines
                    content = b''.join(blocks).decode('utf-8', errors='replace')
                    if content.count('\n') >= n + 1:
                        break

                content = b''.join(blocks).decode('utf-8', errors='replace')
                lines = content.split('\n')

                # Return last n non-empty lines
                return [l for l in lines[-n-1:] if l.strip()]
        except Exception:
            return []

    def tail_files(self, initial_lines=20, poll_interval=0.5):
        """Tail multiple log files with live updates."""
        # Initialize file positions
        for name in self.log_names:
            filepath = self.get_log_path(name)
            if filepath and filepath.exists():
                # Show initial lines
                if initial_lines > 0:
                    for line in self.get_last_lines(filepath, initial_lines):
                        if self.should_show_line(line):
                            print(self.colorize_line(line))

                # Set position to end of file
                self.file_positions[name] = filepath.stat().st_size
            else:
                self.file_positions[name] = 0

        print(f"\n{Colors.DIM}--- Watching logs: {', '.join(self.log_names)} ---{Colors.RESET}\n")

        # Watch for updates
        try:
            while True:
                for name in self.log_names:
                    filepath = self.get_log_path(name)
                    if not filepath:
                        continue

                    if not filepath.exists():
                        continue

                    current_size = filepath.stat().st_size
                    last_pos = self.file_positions.get(name, 0)

                    # File was truncated (rotated)
                    if current_size < last_pos:
                        last_pos = 0

                    # Read new content
                    if current_size > last_pos:
                        try:
                            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                                f.seek(last_pos)
                                new_content = f.read()

                                for line in new_content.split('\n'):
                                    if line.strip() and self.should_show_line(line):
                                        print(self.colorize_line(line))

                                self.file_positions[name] = f.tell()
                        except Exception:
                            pass

                time.sleep(poll_interval)

        except KeyboardInterrupt:
            print(f"\n{Colors.DIM}--- Log tailing stopped ---{Colors.RESET}")


class Command(BaseCommand):
    help = 'Tail log files with live updates and colorized output'

    def add_arguments(self, parser):
        parser.add_argument(
            'logs',
            nargs='*',
            default=[],
            help='Log files to tail (debug, error, orders, delivery, api, security). Default: all'
        )
        parser.add_argument(
            '-n', '--lines',
            type=int,
            default=20,
            help='Number of initial lines to show (default: 20)'
        )
        parser.add_argument(
            '-f', '--filter',
            type=str,
            choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
            help='Filter by minimum log level'
        )
        parser.add_argument(
            '--no-color',
            action='store_true',
            help='Disable colorized output'
        )
        parser.add_argument(
            '-i', '--interval',
            type=float,
            default=0.5,
            help='Poll interval in seconds (default: 0.5)'
        )
        parser.add_argument(
            '-l', '--list',
            action='store_true',
            help='List available log files and exit'
        )

    def handle(self, *args, **options):
        logs_dir = settings.BASE_DIR / 'logs'

        # List available logs
        if options['list']:
            self.stdout.write(self.style.SUCCESS('\nAvailable log files:'))
            for name, filename in LogTailer.LOG_FILES.items():
                filepath = logs_dir / filename
                exists = filepath.exists()
                size = filepath.stat().st_size if exists else 0
                status = f'{size:,} bytes' if exists else 'not found'
                self.stdout.write(f'  {name:12} {filename:20} ({status})')
            self.stdout.write('')
            return

        # Validate log names
        log_names = options['logs'] if options['logs'] else list(LogTailer.LOG_FILES.keys())

        invalid = [n for n in log_names if n not in LogTailer.LOG_FILES]
        if invalid:
            self.stderr.write(
                self.style.ERROR(f"Unknown log(s): {', '.join(invalid)}")
            )
            self.stderr.write(f"Available: {', '.join(LogTailer.LOG_FILES.keys())}")
            return

        # Start tailing
        tailer = LogTailer(
            logs_dir=logs_dir,
            log_names=log_names,
            level_filter=options['filter'],
            colorize=not options['no_color']
        )

        self.stdout.write(self.style.SUCCESS(
            f"\nTailing: {', '.join(log_names)}"
        ))
        if options['filter']:
            self.stdout.write(f"Filter: {options['filter']}+")
        self.stdout.write("Press Ctrl+C to stop\n")

        tailer.tail_files(
            initial_lines=options['lines'],
            poll_interval=options['interval']
        )
