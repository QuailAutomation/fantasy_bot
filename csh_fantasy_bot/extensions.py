"""Extensions registry.

All extensions here are used as singletons and
initialized in application factory
"""
from celery import Celery


celery = Celery()



