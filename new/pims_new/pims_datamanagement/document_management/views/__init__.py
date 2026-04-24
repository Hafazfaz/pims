from .base import HTMXLoginRequiredMixin  # noqa: F401
from .registry_views import (  # noqa: F401
    RegistryHubView,
    RegistryDashboardView,
    StaffWithoutFilesView,
    FileApproveActivationView,
    StaffFolderHubView,
    StaffFolderListView,
    CloseMovementView,
)
from .file_views import (  # noqa: F401
    ExecutiveDashboardView,
    HODDashboardView,
    FileCreateView,
    MyFilesView,
    MessagesView,
    FileRequestActivationView,
    FileRecallView,
    FileDetailView,
    FileUpdateView,
    FileCloseView,
    FileArchiveView,
    DirectorAdminDashboardView,
    FileDeleteView,
    RecordExplorerView,
)
from .document_views import (  # noqa: F401
    DocumentUploadView,
    DocumentDeleteView,
    DocumentDetailView,
    DocumentNewVersionView,
    FileDocumentsView,
    DocumentShareView,
    DocumentDownloadView,
)
DocumentCreateView = DocumentUploadView  # alias for url routing
from .access_views import (  # noqa: F401
    FileAccessRequestListView,
    FileAccessRequestApproveView,
    FileAccessRequestRejectView,
)
from .search_views import (  # noqa: F401
    RecipientSearchView,
    StaffSearchView,
)
from .approval_views import (  # noqa: F401
    MyApprovalChainsView,
    AllActiveChainsView,
    ApprovalReviewView,
    ApprovalChainCreateView,
    ApprovalChainBuilderView,
    ApprovalChainStartView,
    ApprovalStepActionView,
    ApprovalChainDeleteView,
    ChainTemplateListView,
    ChainTemplateBuilderView,
    ChainTemplateDeleteView,
    ApplyChainTemplateView,
)
