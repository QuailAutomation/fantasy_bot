import imaplib
import email
import logging

from email.utils import parsedate_tz, mktime_tz, formatdate

from csh_fantasy_bot.docker_utils import get_docker_secret

logger = logging.getLogger(__name__)

def get_gmail_credential(property, missing_val=None):
    from pathlib import Path
    import configparser
    config = configparser.ConfigParser()
    config.read(f'{Path.home()}/.fantasy/credentials')
    return config['gmail'][property]

GMAIL_USERNAME=get_docker_secret("GMAIL_USERNAME")
if not GMAIL_USERNAME:
    GMAIL_USERNAME = get_gmail_credential("imap_email")

GMAIL_PASSWORD=get_docker_secret("GMAIL_PASSWORD")
if not GMAIL_PASSWORD:
    GMAIL_PASSWORD = get_gmail_credential("imap_password")

def _get_mail_client(email_address, password):
    SMTP_SERVER = "imap.gmail.com"
    SMTP_PORT = 993

    mail = imaplib.IMAP4_SSL(SMTP_SERVER)
    mail.login(email_address, password)
    return mail

def _get_email_ids(mail, label='INBOX', criteria='ALL', max_mails_to_look=10, latest_first=True):
    mail.select(label)
    type, data = mail.search(None, criteria)
    mail_ids = data[0]
    id_list = mail_ids.split()
    # revers so that latest are at front
    id_list.reverse()
    id_list = id_list[: min(len(id_list), max_mails_to_look)]
    return id_list

def search_by_subject(mail, email_ids_list, subject_substring):
    for email_id in email_ids_list:
        msg = get_email_msg(mail, email_id)
        if "Subject" in msg.keys():
            subject = msg.get("Subject", "")
            if subject_substring.lower() in subject.lower():
                return msg
    return None

def get_email_msg(mail, email_id):
    email_id = str(int(email_id))
    type, data = mail.fetch(str(email_id), '(RFC822)')
    for response_part in data:
        if isinstance(response_part, tuple):
            return email.message_from_bytes(response_part[1])

def emails_matching_subject(subj_match_string, earliest_received_date=None, n_matches=1):
    logger.info("Checking gmail for yahoo confirmation")
    mail = _get_mail_client(GMAIL_USERNAME, GMAIL_PASSWORD)
    mail.select('INBOX')
    ids = _get_email_ids(mail)
    message = search_by_subject(mail, ids, subj_match_string)
    # make sure received for email is after passed in earliest_datetime
    if not earliest_received_date or mktime_tz(parsedate_tz(message['Date'])) > earliest_received_date.timestamp():
        ver_code = extract_verification_subject(message['subject'])
        return ver_code
    
yahoo_confirmation_criteria = '(FROM "no-reply@cc.yahoo-inc.com" SUBJECT "Your Yahoo verification code")'
# TODO when i have another use case, let's refactor so generic.  The yahoo specific portion should not be here
def get_last_yahoo_confirmation(earliest_datetime):
    logger.info("Checking gmail for yahoo confirmation")
    mail = _get_mail_client(GMAIL_USERNAME, GMAIL_PASSWORD)
    mail.select('INBOX')
    ids = _get_email_ids(mail, criteria=yahoo_confirmation_criteria)
    assert len(ids) < 2
    message = get_email_msg(mail, ids[0])
    # make sure received for email is after passed in earliest_datetime
    if not earliest_datetime or mktime_tz(parsedate_tz(message['Date'])) > earliest_datetime.timestamp():
        ver_code = extract_verification_subject(message['subject'])
        return ver_code
    

def extract_verification_subject(subject):
    return subject.split('Your Yahoo verification code is')[-1].strip()
