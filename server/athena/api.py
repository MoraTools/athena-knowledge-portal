import hashlib
import hmac
import json
from functools import wraps

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.forms.models import model_to_dict
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .forms import ArticleForm, protect_admin
from .models import ApiKey, Article


def api(view):
    @csrf_exempt
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        # API endpoints accept bearer keys only, never the browser's session cookie.
        scheme, _, token = request.headers.get('Authorization', '').partition(' ')
        key = ApiKey.objects.select_related('user').filter(
            digest=hashlib.sha256(token.encode()).hexdigest(), expires_at__gt=timezone.now()
        ).first() if scheme == 'Bearer' and token else None
        if not key or not key.user.is_active or not hmac.compare_digest(
            key.password_digest, hashlib.sha256(key.user.password.encode()).hexdigest()
        ):
            return JsonResponse({'error': 'A valid Bearer API key is required.'}, status=401,
                                headers={'WWW-Authenticate': 'Bearer'})
        request.user, request.api_key = key.user, key
        try:
            return view(request, *args, **kwargs)
        except Http404:
            return JsonResponse({'error': 'Not found.'}, status=404)
        except ValidationError as error:
            return JsonResponse({'error': error.message_dict if hasattr(error, 'message_dict') else error.messages}, status=400)
        except (ValueError, TypeError, UnicodeDecodeError):
            return JsonResponse({'error': 'Invalid request data.'}, status=400)
        except IntegrityError:
            return JsonResponse({'error': 'The username or article slug already exists.'}, status=409)
    return wrapped


def payload(request):
    if request.content_type != 'application/json':
        raise ValidationError('Use Content-Type: application/json.')
    data = json.loads(request.body)
    if not isinstance(data, dict):
        raise ValidationError('Expected a JSON object.')
    return data


def denied():
    return JsonResponse({'error': 'Permission denied.'}, status=403)


def method_not_allowed(methods):
    return JsonResponse({'error': 'Method not allowed.'}, status=405, headers={'Allow': methods})


def can_edit(request, action):
    return request.api_key.scope in ('articles', 'admin') and request.user.has_perm(f'athena.{action}_article')


def article_data(article, detail=True):
    result = {field: getattr(article, field) for field in
              ('id', 'slug', 'title', 'kind', 'summary', 'author', 'tags', 'published', 'status', 'url', 'download_file')}
    result.update(date=article.date.isoformat(), updated_at=article.updated_at.isoformat(),
                  route=article.get_absolute_url(), pdf=f'/api/v1/articles/{article.slug}/pdf/' if article.pdf_name else None)
    if detail:
        result['body'] = article.body
    return result


def article_form(data, instance=None, files=None):
    fields = ArticleForm.Meta.fields
    unknown = set(data) - set(fields)
    if unknown:
        raise ValidationError('Unknown fields: ' + ', '.join(sorted(unknown)))
    if 'published' in data and not isinstance(data['published'], bool):
        raise ValidationError('published must be a boolean.')
    if 'tags' in data and (not isinstance(data['tags'], list) or any(not isinstance(t, str) or ',' in t for t in data['tags'])):
        raise ValidationError('tags must be a list of strings without commas.')
    if any(not isinstance(value, (str, list, bool)) for value in data.values()):
        raise ValidationError('Invalid field value type.')
    obj = instance or Article()
    values = model_to_dict(obj, fields=fields)
    values.update(data)
    values['tags'] = ', '.join(values.get('tags') or [])
    form = ArticleForm(values, files=files, instance=obj)
    if not form.is_valid():
        raise ValidationError({field: list(errors) for field, errors in form.errors.items()})
    return form


@api
def articles(request, slug=None):
    if request.method not in ('GET', 'POST', 'PATCH', 'DELETE'):
        return method_not_allowed('GET, POST, PATCH, DELETE')
    if request.method == 'GET':
        query = Article.objects.all().defer('pdf')
        if not can_edit(request, 'change'):
            query = query.filter(published=True)
        if slug:
            article = get_object_or_404(query, slug=slug)
            return JsonResponse(article_data(article), headers={'ETag': f'"{article.updated_at.isoformat()}"'})
        if request.GET.get('q'):
            from django.db.models import Q
            q = request.GET['q']
            query = query.filter(Q(title__icontains=q) | Q(summary__icontains=q) | Q(body__icontains=q))
        if request.GET.get('kind'):
            query = query.filter(kind=request.GET['kind'])
        offset = max(0, int(request.GET.get('offset', 0)))
        limit = max(1, min(100, int(request.GET.get('limit', 50))))
        return JsonResponse({'count': query.count(), 'offset': offset, 'limit': limit,
                             'results': [article_data(a, False) for a in query[offset:offset + limit]]})
    action = {'POST': 'add', 'PATCH': 'change', 'DELETE': 'delete'}[request.method]
    if not can_edit(request, action):
        return denied()
    if request.method == 'POST' and slug or request.method != 'POST' and not slug:
        return method_not_allowed('GET, PATCH, DELETE' if slug else 'GET, POST')
    with transaction.atomic():
        article = get_object_or_404(Article, slug=slug) if slug else None
        if article and request.headers.get('If-Match') != f'"{article.updated_at.isoformat()}"':
            return JsonResponse({'error': 'Read the article and send its ETag in If-Match before changing it.'}, status=412)
        if request.method == 'DELETE':
            article.delete()
            return HttpResponse(status=204)
        data = payload(request)
        if article and 'slug' in data and data['slug'] != article.slug:
            raise ValidationError('Article slugs cannot be changed.')
        article = article_form(data, article).save()
        return JsonResponse(article_data(article), status=201 if request.method == 'POST' else 200,
                            headers={'ETag': f'"{article.updated_at.isoformat()}"'})


@api
def article_upload(request, slug, kind):
    article = get_object_or_404(Article, slug=slug)
    if request.method == 'GET' and kind == 'pdf':
        if not article.published and not can_edit(request, 'change'):
            return denied()
        if not article.pdf:
            raise Http404
        return HttpResponse(bytes(article.pdf), content_type='application/pdf',
                            headers={'Content-Disposition': f'attachment; filename="{article.slug}.pdf"'})
    if request.method != 'POST':
        return method_not_allowed('GET, POST' if kind == 'pdf' else 'POST')
    if not can_edit(request, 'change'):
        return denied()
    if 'file' not in request.FILES:
        raise ValidationError('Send a multipart/form-data file field.')
    with transaction.atomic():
        article.refresh_from_db()
        if request.headers.get('If-Match') != f'"{article.updated_at.isoformat()}"':
            return JsonResponse({'error': 'Send the current article ETag in If-Match.'}, status=412)
        article = article_form({}, article, {f'{kind}_file': request.FILES['file']}).save()
        return JsonResponse(article_data(article), headers={'ETag': f'"{article.updated_at.isoformat()}"'})


def user_data(user):
    return {'id': user.pk, 'username': user.username, 'email': user.email, 'active': user.is_active,
            'admin': user.is_superuser, 'first_name': user.first_name, 'last_name': user.last_name}


@api
def users(request, user_id=None):
    if request.api_key.scope != 'admin' or not request.user.is_superuser:
        return denied()
    if request.method == 'GET':
        if user_id:
            return JsonResponse(user_data(get_object_or_404(User, pk=user_id)))
        return JsonResponse({'results': [user_data(u) for u in User.objects.order_by('username')]})
    if request.method not in ('POST', 'PATCH', 'DELETE'):
        return method_not_allowed('GET, POST, PATCH, DELETE')
    if request.method == 'POST' and user_id or request.method != 'POST' and not user_id:
        return method_not_allowed('GET, PATCH, DELETE' if user_id else 'GET, POST')
    with transaction.atomic():
        user = get_object_or_404(User, pk=user_id) if user_id else User()
        if request.method == 'DELETE':
            protect_admin(user, actor=request.user, deleting=True)
            user.delete()
            return HttpResponse(status=204)
        data = payload(request)
        if set(data) - {'username', 'email', 'password', 'active', 'admin', 'first_name', 'last_name'}:
            raise ValidationError('Unknown user fields.')
        if any(not isinstance(v, bool) if k in ('active', 'admin') else not isinstance(v, str) for k, v in data.items()):
            raise ValidationError('User fields must be strings; active and admin must be booleans.')
        active, admin = data.get('active', user.is_active), data.get('admin', user.is_superuser)
        if user.pk:
            protect_admin(user, actor=request.user, active=active, admin=admin)
        for field in ('username', 'email', 'first_name', 'last_name'):
            if field in data:
                setattr(user, field, data[field])
        user.is_active, user.is_superuser, user.is_staff = active, admin, admin
        if not user_id and 'password' not in data:
            raise ValidationError('A password is required.')
        if 'password' in data:
            validate_password(data['password'], user)
            user.set_password(data['password'])
        user.full_clean()
        user.save()
        return JsonResponse(user_data(user), status=201 if request.method == 'POST' else 200)
