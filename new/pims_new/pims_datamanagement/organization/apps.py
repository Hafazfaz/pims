from django.apps import AppConfig


class OrganizationConfig(AppConfig):
    name = 'organization'

    def ready(self):
        import organization.signals  # noqa
