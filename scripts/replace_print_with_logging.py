#!/usr/bin/env python3
"""
Script to help convert print statements to logging calls.
This is a semi-automated tool - ALWAYS review changes manually!

Usage:
    # Preview changes (dry run)
    python scripts/replace_print_with_logging.py

    # Apply changes
    python scripts/replace_print_with_logging.py --commit

    # Process specific file
    python scripts/replace_print_with_logging.py --file orders/views.py
"""

import re
import os
import sys
from pathlib import Path

def analyze_print_statement(line, line_num):
    """Analyze a print statement and suggest logging level."""
    line_lower = line.lower()

    # Determine logging level based on content
    if any(word in line_lower for word in ['error', 'exception', 'failed', 'failure', 'critical']):
        return 'error'
    elif any(word in line_lower for word in ['warning', 'warn', 'deprecated', 'caution']):
        return 'warning'
    elif any(word in line_lower for word in ['step', 'processing', 'fetching', 'created', 'updated', 'starting', 'completed', 'success']):
        return 'info'
    else:
        return 'debug'

def check_logger_import(lines):
    """Check if logging import exists in file."""
    has_logging_import = False
    has_logger_declaration = False

    for line in lines:
        if re.match(r'^import logging', line) or re.match(r'^from logging import', line):
            has_logging_import = True
        if re.match(r'^logger\s*=\s*logging\.getLogger', line):
            has_logger_declaration = True

    return has_logging_import, has_logger_declaration

def add_logging_import(lines, file_path):
    """Add logging import and logger declaration to file if missing."""
    has_logging_import, has_logger_declaration = check_logger_import(lines)

    # Determine appropriate logger name based on file path
    if 'orders/' in str(file_path):
        logger_name = 'orders'
    elif 'delivery/' in str(file_path):
        logger_name = 'delivery'
    elif 'business/' in str(file_path):
        logger_name = 'business'
    elif 'fleet/' in str(file_path):
        logger_name = 'fleet'
    elif 'ezzy_api/' in str(file_path):
        logger_name = 'ezzy_api'
    elif 'core/' in str(file_path):
        logger_name = 'core'
    elif 'product/' in str(file_path):
        logger_name = 'product'
    elif 'webpages/' in str(file_path):
        logger_name = 'webpages'
    else:
        logger_name = '__name__'

    new_lines = []
    import_added = False
    logger_added = False

    for i, line in enumerate(lines):
        # Add logging import after other imports
        if not import_added and not has_logging_import:
            if line.startswith('from django') or line.startswith('import django'):
                new_lines.append(line)
                # Check if next line is also an import
                if i + 1 < len(lines) and (lines[i + 1].startswith('import') or lines[i + 1].startswith('from')):
                    continue
                else:
                    new_lines.append('import logging\n')
                    import_added = True
                continue

        # Add logger declaration after imports, before class/function definitions
        if not logger_added and not has_logger_declaration:
            if (line.startswith('def ') or line.startswith('class ') or line.startswith('@')):
                new_lines.append(f'\nlogger = logging.getLogger(\'{logger_name}\')\n\n')
                logger_added = True

        new_lines.append(line)

    # If we couldn't find a good place, add at the beginning after docstring
    if not import_added and not has_logging_import:
        # Find end of docstring
        insert_pos = 0
        in_docstring = False
        for i, line in enumerate(new_lines):
            if '"""' in line or "'''" in line:
                if not in_docstring:
                    in_docstring = True
                else:
                    insert_pos = i + 1
                    break

        new_lines.insert(insert_pos, 'import logging\n')

    if not logger_added and not has_logger_declaration:
        new_lines.insert(insert_pos + 1, f'logger = logging.getLogger(\'{logger_name}\')\n\n')

    return new_lines

def convert_print_to_logging(file_path, dry_run=True, show_details=True):
    """Convert print statements to logging calls in a Python file."""
    if show_details:
        print(f"\n{'='*60}")
        print(f"Processing: {file_path}")
        print(f"{'='*60}")

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"❌ Error reading {file_path}: {e}")
        return 0

    changes = []
    new_lines = []

    for i, line in enumerate(lines, 1):
        # Match print statements (various patterns)
        if re.match(r'^\s*print\(', line):
            level = analyze_print_statement(line, i)

            # Extract indentation
            indent = re.match(r'^(\s*)', line).group(1)

            # Extract print content - handle multi-line prints
            content_match = re.search(r'print\((.*?)\)\s*(?:#.*)?$', line)
            if content_match:
                content = content_match.group(1).strip()

                # Handle empty prints
                if not content or content == '':
                    content = '""'

                # Create logging statement
                new_line = f'{indent}logger.{level}({content})\n'

                changes.append({
                    'line_num': i,
                    'old': line.rstrip(),
                    'new': new_line.rstrip(),
                    'level': level
                })

                new_lines.append(new_line)
            else:
                # If we can't parse it, keep original
                new_lines.append(line)
        else:
            new_lines.append(line)

    # Add logging import if needed
    if changes and not dry_run:
        new_lines = add_logging_import(new_lines, file_path)

    # Print summary
    if show_details:
        print(f"\nFound {len(changes)} print statements to convert:")
        display_limit = 10 if len(changes) > 10 else len(changes)

        for change in changes[:display_limit]:
            print(f"\nLine {change['line_num']}: [{change['level'].upper()}]")
            print(f"  - {change['old']}")
            print(f"  + {change['new']}")

        if len(changes) > display_limit:
            print(f"\n... and {len(changes) - display_limit} more changes")

    if not dry_run and changes:
        try:
            # Write changes
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            print(f"\n✅ Converted {len(changes)} print statements in {file_path}")
        except Exception as e:
            print(f"❌ Error writing {file_path}: {e}")
            return 0

    return len(changes)

def main():
    # Files with print statements (from grep results)
    default_files = [
        'orders/views.py',      # 83 prints
        'business/views.py',    # 76 prints
        'core/views.py',        # 54 prints
        'fleet/views.py',       # 25 prints
        'delivery/views.py',    # 20 prints
        'orders/models.py',     # 7 prints
        'product/views.py',     # 6 prints
        'orders/signals.py',    # 4 prints
        'ezzy_api/views.py',    # 3 prints
        'webpages/views.py',    # 2 prints
        'fleet/signals.py',     # 2 prints
        'webpages/forms.py',    # 1 print
    ]

    # Parse command line arguments
    dry_run = '--commit' not in sys.argv
    specific_file = None

    for i, arg in enumerate(sys.argv):
        if arg == '--file' and i + 1 < len(sys.argv):
            specific_file = sys.argv[i + 1]
            break

    # Determine base directory
    base_dir = Path(__file__).resolve().parent.parent

    if dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")
        print("Use --commit flag to apply changes\n")
    else:
        print("⚠️  COMMIT MODE - Changes will be written to files")
        print("Make sure you have committed your current work!\n")
        response = input("Continue? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print("Aborted.")
            return

    # Determine which files to process
    if specific_file:
        files = [specific_file]
        print(f"\n📝 Processing single file: {specific_file}\n")
    else:
        files = default_files
        print(f"📝 Processing {len(files)} files\n")

    total_changes = 0
    successful_files = 0
    failed_files = []

    for file_rel in files:
        file_path = base_dir / file_rel
        if file_path.exists():
            try:
                count = convert_print_to_logging(file_path, dry_run, show_details=True)
                total_changes += count
                if count > 0:
                    successful_files += 1
            except Exception as e:
                print(f"❌ Error processing {file_path}: {e}")
                failed_files.append(str(file_rel))
        else:
            print(f"⚠️  File not found: {file_path}")
            failed_files.append(str(file_rel))

    # Final summary
    print(f"\n{'='*60}")
    print(f"📊 SUMMARY")
    print(f"{'='*60}")
    print(f"Total files processed: {len(files)}")
    print(f"Files with changes: {successful_files}")
    print(f"Total print statements found: {total_changes}")

    if failed_files:
        print(f"\n⚠️  Failed files ({len(failed_files)}):")
        for f in failed_files:
            print(f"  - {f}")

    if dry_run:
        print(f"\n💡 This was a dry run. Run with --commit flag to apply changes.")
    else:
        print(f"\n✅ All changes applied successfully!")
        print(f"\n📋 Next steps:")
        print(f"  1. Review changes: git diff")
        print(f"  2. Test the application: python manage.py runserver")
        print(f"  3. Run tests: python manage.py test")
        print(f"  4. If all looks good, commit: git add . && git commit -m 'refactor: Replace print statements with logging'")

    print(f"{'='*60}\n")

if __name__ == '__main__':
    main()
