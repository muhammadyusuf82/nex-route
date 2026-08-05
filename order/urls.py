from rest_framework.routers import DefaultRouter
from .views import ItemViewSet, TodoViewSet

router = DefaultRouter()
router.register(r"items", ItemViewSet, basename="item")
router.register(r"todos", TodoViewSet, basename="todo")

urlpatterns = router.urls
