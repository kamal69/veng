import sys
from django.apps import AppConfig


class ReportsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'reports'

    def ready(self):
        # Python 3.14 compatibility patch for Django 4.2 BaseContext.__copy__
        # where copy(super()) in Django 4.2 fails under Python 3.14
        if sys.version_info >= (3, 14):
            from django.template.context import BaseContext

            def _basecontext_copy(self):
                duplicate = object.__new__(self.__class__)
                duplicate.__dict__.update(self.__dict__)
                duplicate.dicts = self.dicts[:]
                return duplicate

            BaseContext.__copy__ = _basecontext_copy
