from django.apps import AppConfig


class CallsConfig(AppConfig):
    name = 'calls'

    def ready(self):
        import calls.signals
