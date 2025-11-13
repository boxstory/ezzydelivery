#!/usr/bin/env python
"""
Compile custom Bootstrap SCSS to CSS using libsass
"""
import sass
import os

# Get the directory of this script
script_dir = os.path.dirname(os.path.abspath(__file__))

# Bootstrap SCSS source directory
bootstrap_scss_dir = os.path.join(script_dir, 'bootstrap-5.3.2', 'scss')

# Custom SCSS file
custom_scss_file = os.path.join(script_dir, 'custom-bootstrap.scss')

# Output CSS file (in parent css directory)
output_css_file = os.path.join(script_dir, '..', 'css', 'bootstrap-custom.css')
output_css_min_file = os.path.join(script_dir, '..', 'css', 'bootstrap-custom.min.css')

print(f"Bootstrap SCSS directory: {bootstrap_scss_dir}")
print(f"Custom SCSS file: {custom_scss_file}")
print(f"Output CSS file: {output_css_file}")
print(f"Output minified CSS file: {output_css_min_file}")

# Read custom SCSS
with open(custom_scss_file, 'r', encoding='utf-8') as f:
    custom_scss = f.read()

print("\nCompiling expanded CSS...")
# Compile expanded CSS (for development/debugging)
try:
    compiled_css = sass.compile(
        string=custom_scss,
        include_paths=[bootstrap_scss_dir],
        output_style='expanded'
    )
    with open(output_css_file, 'w', encoding='utf-8') as f:
        f.write(compiled_css)

    # Get file size
    size_kb = os.path.getsize(output_css_file) / 1024
    print(f"[OK] Expanded CSS compiled successfully: {size_kb:.2f} KB")
except Exception as e:
    print(f"[ERROR] Error compiling expanded CSS: {e}")
    exit(1)

print("\nCompiling compressed CSS...")
# Compile compressed CSS (for production)
try:
    compiled_css_min = sass.compile(
        string=custom_scss,
        include_paths=[bootstrap_scss_dir],
        output_style='compressed'
    )
    with open(output_css_min_file, 'w', encoding='utf-8') as f:
        f.write(compiled_css_min)

    # Get file size
    size_kb_min = os.path.getsize(output_css_min_file) / 1024
    print(f"[OK] Compressed CSS compiled successfully: {size_kb_min:.2f} KB")
except Exception as e:
    print(f"[ERROR] Error compiling compressed CSS: {e}")
    exit(1)

# Compare with CDN Bootstrap size (approx 226 KB minified)
cdn_size = 226
reduction = ((cdn_size - size_kb_min) / cdn_size) * 100

print(f"\n{'='*60}")
print(f"BUILD COMPLETE")
print(f"{'='*60}")
print(f"Expanded CSS:   {size_kb:.2f} KB")
print(f"Minified CSS:   {size_kb_min:.2f} KB")
print(f"CDN Bootstrap:  ~{cdn_size} KB")
print(f"Size Reduction: {reduction:.1f}%")
print(f"{'='*60}")
