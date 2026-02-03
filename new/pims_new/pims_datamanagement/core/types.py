from enum import Enum

class StaffType(Enum):
    PERMANENT = 'permanent'
    LOCUM = 'locum'
    CONTRACT = 'contract'
    NYSC = 'nysc'

    @classmethod
    def choices(cls):
        return [(key.value, key.name.title()) for key in cls]

class FileType(Enum):
    PERSONAL = 'personal'
    POLICY = 'policy'

    @classmethod
    def choices(cls):
        return [(key.value, key.name.title()) for key in cls]

class FileStatus(Enum):
    INACTIVE = 'inactive'
    PENDING_ACTIVATION = 'pending_activation'
    ACTIVE = 'active'
    IN_TRANSIT = 'in_transit'
    CLOSED = 'closed'
    ARCHIVED = 'archived'

    @classmethod
    def choices(cls):
        return [(key.value, key.name.replace('_', ' ').title()) for key in cls]
