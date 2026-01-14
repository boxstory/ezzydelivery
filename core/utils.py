"""
Core Utilities Module
=====================

Shared utility functions used across multiple apps.

Functions:
    - contains_arabic: Check if text contains Arabic characters
    - translate_to_english: Translate Arabic text to English
    - convert_arabic_numerals: Convert Arabic numerals to English
    - format_whatsapp_number: Format phone number for WhatsApp
"""

import logging
import re

logger = logging.getLogger(__name__)

# Translation support for Arabic text
try:
    from deep_translator import GoogleTranslator
    translator_available = True
except ImportError:
    translator_available = False
    logger.warning("deep_translator not installed. Arabic translation disabled.")


def contains_arabic(text):
    """
    Check if text contains Arabic characters.

    Args:
        text: String to check

    Returns:
        bool: True if text contains Arabic characters
    """
    if not text:
        return False
    # Arabic Unicode range: \u0600-\u06FF (Arabic), \u0750-\u077F (Arabic Supplement)
    arabic_pattern = re.compile(r'[\u0600-\u06FF\u0750-\u077F]')
    return bool(arabic_pattern.search(str(text)))


def translate_to_english(text):
    """
    Translate Arabic text to English using Google Translator.
    Returns original text if translation fails or text is not Arabic.

    Args:
        text: String to translate

    Returns:
        str: Translated text or original if translation not needed/failed
    """
    if not text or not translator_available:
        return text

    try:
        # Only translate if text contains Arabic
        if contains_arabic(text):
            translator = GoogleTranslator(source='ar', target='en')
            translated = translator.translate(str(text))
            return translated if translated else text
        return text
    except Exception as e:
        logger.warning(f"Translation failed for text: {str(text)[:50]}... Error: {e}")
        return text


def convert_arabic_numerals(text):
    """
    Convert Arabic/Eastern Arabic numerals to English numerals.

    Args:
        text: String containing numerals to convert

    Returns:
        str: Text with Arabic numerals replaced by English numerals
    """
    if not text:
        return text

    # Arabic-Indic digits (٠١٢٣٤٥٦٧٨٩) used in Arabic countries
    arabic_numerals = '٠١٢٣٤٥٦٧٨٩'
    # Extended Arabic-Indic digits (۰۱۲۳۴۵۶۷۸۹) used in Persian/Urdu
    persian_numerals = '۰۱۲۳۴۵۶۷۸۹'
    english_numerals = '0123456789'

    result = str(text)
    for i, digit in enumerate(arabic_numerals):
        result = result.replace(digit, english_numerals[i])
    for i, digit in enumerate(persian_numerals):
        result = result.replace(digit, english_numerals[i])

    return result


def format_whatsapp_number(phone):
    """
    Format phone number for WhatsApp.

    Rules:
        - Remove + sign and spaces
        - For 8-digit Qatar numbers starting with 3, 5, 6, 7: add 974
        - Numbers starting with 4 are landlines (skip country code)
        - For other numbers, keep with country code

    Args:
        phone: Phone number string to format

    Returns:
        str: Formatted phone number for WhatsApp
    """
    if not phone:
        return ''

    # Convert Arabic numerals first
    phone = convert_arabic_numerals(str(phone))

    # Remove +, spaces, dashes, and other common separators
    clean_phone = phone.replace('+', '').replace(' ', '').replace('-', '').replace('(', '').replace(')', '')

    # Remove any remaining non-digit characters
    digits_only = ''.join(c for c in clean_phone if c.isdigit())

    if not digits_only:
        return ''

    # Check if it's an 8-digit Qatar mobile number (starts with 3, 5, 6, or 7)
    if len(digits_only) == 8 and digits_only[0] in '3567':
        return '974' + digits_only

    # If it's an 8-digit number starting with 4 (Qatar landline), don't add country code
    if len(digits_only) == 8 and digits_only[0] == '4':
        return digits_only  # Landline, no WhatsApp formatting needed

    # If already has country code (more than 8 digits), return as is
    return digits_only
