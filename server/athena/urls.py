from django.contrib import admin
from django.contrib.auth import views as auth
from django.urls import path, re_path
from django.views.generic import RedirectView

from . import api, views

urlpatterns = [
    path('healthz', views.health),
    path('admin/', admin.site.urls),
    path('accounts/login/', auth.LoginView.as_view()),
    path('accounts/logout/', auth.LogoutView.as_view()),
    path('accounts/profile/', views.account),
    path('accounts/password_change/', auth.PasswordChangeView.as_view(success_url='/accounts/profile/')),
    path('request-access', RedirectView.as_view(url='/accounts/login/')),
    path('request-access.html', RedirectView.as_view(url='/accounts/login/')),
    path('api/v1/articles/', api.articles),
    path('api/v1/articles/<slug:slug>/', api.articles),
    re_path(r'^api/v1/articles/(?P<slug>[a-z0-9-]+)/(?P<kind>pdf|markdown)/$', api.article_upload),
    path('api/v1/users/', api.users),
    path('api/v1/users/<int:user_id>/', api.users),
    path('api/openapi.json', views.api_schema),
    path('search-index.json', views.search_index),
    re_path(r'^content/(?P<slug>[a-z0-9-]+)(?:\.md)?$', views.article_markdown),
    path('pdf/<slug:slug>.pdf', views.pdf),
    re_path(r'^(?P<section>guides|tools|updates)\.md$', views.library),
    path('', views.static_portal),
    path('<path:path>', views.static_portal),
]
