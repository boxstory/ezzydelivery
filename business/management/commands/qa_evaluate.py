"""
QA Evaluation Management Command

This command helps evaluate pages and track UI/CSS issues.
Usage:
    python manage.py qa_evaluate --list-urls
    python manage.py qa_evaluate --check-templates
    python manage.py qa_evaluate --update-todos

--update-todos runs scripts/qa_scan.py, which regenerates
.claude/docs/12-testing-qa/qa_todos.md from a fresh scan of the codebase while
preserving any human triage marks already in the file.
"""

import os
import subprocess
import sys
from django.core.management.base import BaseCommand
from django.urls import get_resolver, URLPattern, URLResolver
from django.conf import settings


class Command(BaseCommand):
    help = 'QA evaluation helper - lists URLs and checks templates for review'

    def add_arguments(self, parser):
        parser.add_argument(
            '--list-urls',
            action='store_true',
            help='List all URLs in the project for evaluation',
        )
        parser.add_argument(
            '--check-templates',
            action='store_true',
            help='Check template files for common issues',
        )
        parser.add_argument(
            '--update-todos',
            action='store_true',
            help='Re-scan the codebase and regenerate qa_todos.md (preserves triage marks)',
        )
        parser.add_argument(
            '--app',
            type=str,
            help='Filter by app name (e.g., business, orders)',
        )

    def handle(self, *args, **options):
        if options['list_urls']:
            self.list_urls(options.get('app'))
        elif options['check_templates']:
            self.check_templates(options.get('app'))
        elif options['update_todos']:
            self.update_todos()
        else:
            self.stdout.write(self.style.WARNING(
                'Please specify an action: --list-urls, --check-templates, or --update-todos'
            ))

    def list_urls(self, app_filter=None):
        """List all URLs for QA evaluation"""
        self.stdout.write(self.style.SUCCESS('\n=== URLs for QA Evaluation ===\n'))

        resolver = get_resolver()
        urls = self._get_all_urls(resolver, prefix='')

        # Group by app
        apps = {}
        for url, name, callback in urls:
            if name:
                app_name = name.split(':')[0] if ':' in name else 'root'
            else:
                app_name = 'unnamed'

            if app_filter and app_name != app_filter:
                continue

            if app_name not in apps:
                apps[app_name] = []
            apps[app_name].append((url, name, callback))

        for app, app_urls in sorted(apps.items()):
            self.stdout.write(self.style.HTTP_INFO(f'\n[{app}]'))
            for url, name, callback in app_urls:
                view_name = callback.__name__ if callback else 'N/A'
                self.stdout.write(f'  /{url}')
                self.stdout.write(f'    Name: {name or "unnamed"}')
                self.stdout.write(f'    View: {view_name}')

    def _get_all_urls(self, resolver, prefix=''):
        """Recursively get all URL patterns"""
        urls = []
        for pattern in resolver.url_patterns:
            if isinstance(pattern, URLResolver):
                new_prefix = prefix + str(pattern.pattern)
                urls.extend(self._get_all_urls(pattern, new_prefix))
            elif isinstance(pattern, URLPattern):
                url = prefix + str(pattern.pattern)
                callback = pattern.callback
                name = pattern.name
                if hasattr(resolver, 'namespace') and resolver.namespace:
                    name = f"{resolver.namespace}:{name}" if name else None
                urls.append((url, name, callback))
        return urls

    def check_templates(self, app_filter=None):
        """Check templates for common CSS/alignment issues"""
        self.stdout.write(self.style.SUCCESS('\n=== Template Check ===\n'))

        template_dirs = []

        # Get template directories
        for template_config in settings.TEMPLATES:
            template_dirs.extend(template_config.get('DIRS', []))

        # Also check app template directories
        apps_to_check = ['business', 'orders', 'product', 'workforce']
        if app_filter:
            apps_to_check = [app_filter]

        for app in apps_to_check:
            app_template_dir = os.path.join(settings.BASE_DIR, app, 'templates')
            if os.path.exists(app_template_dir):
                template_dirs.append(app_template_dir)

        issues = []

        for template_dir in template_dirs:
            if not os.path.exists(template_dir):
                continue

            for root, dirs, files in os.walk(template_dir):
                for file in files:
                    if file.endswith('.html'):
                        filepath = os.path.join(root, file)
                        file_issues = self._check_template_file(filepath)
                        if file_issues:
                            issues.append((filepath, file_issues))

        if issues:
            for filepath, file_issues in issues:
                rel_path = os.path.relpath(filepath, settings.BASE_DIR)
                self.stdout.write(self.style.WARNING(f'\n{rel_path}:'))
                for issue in file_issues:
                    self.stdout.write(f'  - {issue}')
        else:
            self.stdout.write(self.style.SUCCESS('No common issues found in templates'))

    def _check_template_file(self, filepath):
        """Check a single template file for common issues"""
        issues = []

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
        except Exception as e:
            return [f'Could not read file: {e}']

        # Check for common issues
        checks = [
            ('style="', 'Inline styles found (consider using CSS classes)'),
            ('onclick="', 'Inline onclick handlers (consider using event listeners)'),
            ('!important', 'CSS !important usage detected'),
            ('float:', 'Float-based layout detected (consider flexbox/grid)'),
        ]

        for pattern, message in checks:
            if pattern in content:
                count = content.count(pattern)
                issues.append(f'{message} ({count} occurrences)')

        # Check for missing responsive meta
        if '<meta name="viewport"' not in content and '{% extends' not in content:
            if '<html' in content:
                issues.append('Missing viewport meta tag')

        # Check for accessibility
        img_count = content.count('<img')
        alt_count = content.count('alt="')
        if img_count > alt_count:
            issues.append(f'Images may be missing alt attributes ({img_count} images, {alt_count} alt attrs)')

        return issues

    def update_todos(self):
        """Regenerate qa_todos.md by running the scanner.

        This used to only rewrite a `Last Updated:` line, and pointed at docs/qa_todos.md —
        a path that stopped existing when docs moved under .claude/docs/. The result was a
        file that looked maintained and was not. Now it re-scans for real.
        """
        scanner = os.path.join(settings.BASE_DIR, 'scripts', 'qa_scan.py')

        if not os.path.exists(scanner):
            self.stdout.write(self.style.ERROR(f'Scanner not found: {scanner}'))
            return

        result = subprocess.run(
            [sys.executable, scanner],
            capture_output=True, text=True, cwd=settings.BASE_DIR,
        )

        if result.stdout:
            self.stdout.write(result.stdout.rstrip())

        if result.returncode != 0:
            self.stdout.write(self.style.ERROR(
                f'qa_scan.py failed (exit {result.returncode}):\n{result.stderr.rstrip()}'
            ))
            return

        self.stdout.write(self.style.SUCCESS('qa_todos.md regenerated — triage marks preserved.'))
