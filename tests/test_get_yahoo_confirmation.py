import pytest
import datetime

from csh_fantasy_bot.google_email import get_last_yahoo_confirmation, extract_verification_subject


def test_get_yahoo_confirmation():
    now = datetime.datetime.utcnow()
    code = get_last_yahoo_confirmation(now)
    assert code == 'test'

def test_parse_code_subject():
    subject = 'Your Yahoo verification code is HHPQVHBG'
    ver_code = extract_verification_subject(subject)
    assert ver_code == 'HHPQVHBG'
    pass


