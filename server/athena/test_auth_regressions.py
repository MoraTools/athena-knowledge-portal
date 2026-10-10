import hashlib
import json
import tempfile
from pathlib import Path

from django.contrib.auth.models import Group, Permission, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .forms import ADMIN_VIEW, EDIT_AREAS, DirectoryUserForm, SafeUserChangeForm, held_areas, permissions
from .models import ApiKey, Article, LoginAttempt


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False,
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class AdminAuthRegressionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.root = User.objects.create_superuser('root', password='Root-Example-8824!')
        cls.reader = User.objects.create_user('reader', password='Reader-Example-8824!')
        cls.manager = User.objects.create_user('manager', is_staff=True, password='Manager-Example-8824!')
        cls.manager.user_permissions.set(permissions([
            'auth.add_user', 'auth.change_user', 'auth.delete_user', 'auth.view_user',
            'athena.add_apikey', 'athena.change_apikey', 'athena.delete_apikey', 'athena.view_apikey',
            'athena.view_article', 'athena.view_download']))
        cls.editor = User.objects.create_user('editor', is_staff=True, password='Editor-Example-8824!')
        cls.editor.user_permissions.set(permissions(['athena.change_article']))
        cls.article = Article.objects.create(title='Guide', slug='guide', summary='Summary', author='Author',
                                             body='# Guide\nOriginal body', published=True, is_public=True)

    def setUp(self):
        self.enterContext(override_settings(DATA_DIR=Path(self.enterContext(tempfile.TemporaryDirectory()))))
        self.client.force_login(self.manager)

    def key_data(self, owner, scope='admin'):
        return {'name': 'agent', 'user': owner.pk, 'scope': scope,
                'expires_at_0': '2099-01-01', 'expires_at_1': '00:00:00'}

    def issue_key(self, owner, scope='admin'):
        key = ApiKey(user=owner, scope=scope, name='existing')
        raw = key.issue()
        key.save()
        return key, raw

    def popup_data(self, user, **changes):
        joined = timezone.localtime(user.date_joined)
        data = {'username': user.username, 'first_name': 'Updated', '_popup': '1',
                'is_active': 'on', 'date_joined_0': joined.strftime('%Y-%m-%d'),
                'date_joined_1': joined.strftime('%H:%M:%S')}
        data.update(changes)
        return data

    def article_data(self, **changes):
        data = {'title': self.article.title, 'slug': self.article.slug, 'kind': 'guide',
                'summary': self.article.summary, 'author': self.article.author, 'date': self.article.date.isoformat(),
                'tags': '', 'body': self.article.body, 'published': 'on', 'is_public': 'True',
                'loaded_revision': self.article.updated_at.isoformat(), '_continue': '1'}
        data.update(changes)
        return data

    def test_key_owner_selector_and_tampered_post_enforce_owner_ceiling(self):
        response = self.client.get('/admin/athena/apikey/add/')
        owners = response.context['adminform'].form.fields['user'].queryset
        self.assertEqual(set(owners.values_list('pk', flat=True)), {self.manager.pk, self.reader.pk})
        for owner in [self.root, self.editor]:
            for scope in ['read', 'articles', 'admin']:
                with self.subTest(owner=owner.username, scope=scope):
                    response = self.client.post('/admin/athena/apikey/add/', self.key_data(owner, scope))
                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(response.context['adminform'].form.errors)
                    self.assertFalse(ApiKey.objects.exists())

    def test_permitted_keys_show_raw_token_once_and_keep_owner_api_ceiling(self):
        for owner, scope in [(self.reader, 'read'), (self.manager, 'admin')]:
            with self.subTest(owner=owner.username, scope=scope):
                response = self.client.post('/admin/athena/apikey/add/', self.key_data(owner, scope))
                self.assertEqual(response.status_code, 200)
                raw = response.context['raw']
                self.assertTrue(raw.startswith('athena_'))
                key = ApiKey.objects.get(user=owner)
                self.assertNotEqual(key.digest, raw)
                self.assertEqual(key.digest, hashlib.sha256(raw.encode()).hexdigest())
                response = self.client.get('/api/v1/me/', HTTP_AUTHORIZATION='Bearer ' + raw)
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.json()['user']['is_superuser'])
                self.assertFalse(response.json()['can']['write_articles'])
                self.assertFalse(response.json()['can']['manage_users'])
                self.assertNotContains(self.client.get(f'/admin/athena/apikey/{key.pk}/change/'), raw)
                self.assertNotContains(self.client.get('/admin/athena/apikey/'), raw)

    def test_partial_manager_cannot_change_delete_or_bulk_delete_higher_owner_keys(self):
        protected, _ = self.issue_key(self.root)
        safe, _ = self.issue_key(self.reader, 'read')
        for path in [f'/admin/athena/apikey/{protected.pk}/change/',
                     f'/admin/athena/apikey/{protected.pk}/delete/']:
            self.assertEqual(self.client.post(path, {'name': 'Tampered', 'post': 'yes'}).status_code, 403)
        response = self.client.post('/admin/athena/apikey/', {
            'action': 'delete_selected', '_selected_action': [protected.pk, safe.pk], 'post': 'yes'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(ApiKey.objects.count(), 2)
        response = self.client.post(f'/admin/athena/apikey/{safe.pk}/change/', {
            'name': 'Renamed', 'expires_at_0': '2098-01-01', 'expires_at_1': '00:00:00'})
        self.assertEqual(response.status_code, 302)
        safe.refresh_from_db()
        self.assertEqual(safe.name, 'Renamed')
        self.assertEqual(self.client.post(f'/admin/athena/apikey/{safe.pk}/delete/', {'post': 'yes'}).status_code, 302)
        self.assertFalse(ApiKey.objects.filter(pk=safe.pk).exists())

    def test_superuser_can_issue_keys_to_superusers(self):
        self.client.force_login(self.root)
        response = self.client.post('/admin/athena/apikey/add/', self.key_data(self.root))
        self.assertEqual(response.status_code, 200)
        response = self.client.get('/api/v1/me/', HTTP_AUTHORIZATION='Bearer ' + response.context['raw'])
        self.assertTrue(response.json()['can']['manage_users'])

    def test_popup_change_rejects_superuser_direct_permission_and_group_escalation(self):
        group = Group.objects.create(name='Article editors')
        group.permissions.add(Permission.objects.get(codename='change_article', content_type__app_label='athena'))
        path = f'/admin/auth/user/{self.reader.pk}/change/?_popup=1'
        grants = [{'is_superuser': 'on'}, {'user_permissions': [group.permissions.get().pk]}, {'groups': [group.pk]}]
        for grant in grants:
            with self.subTest(grant=grant):
                response = self.client.post(path, self.popup_data(self.reader, is_staff='on', **grant))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['adminform'].form.errors)
                self.reader.refresh_from_db()
                self.assertFalse(self.reader.is_superuser or self.reader.is_staff)
                self.assertFalse(self.reader.user_permissions.exists() or self.reader.groups.exists())

    def test_native_change_form_shared_validation_rejects_unfiltered_group_and_permission_grants(self):
        grant = Permission.objects.get(codename='change_article', content_type__app_label='athena')
        group = Group.objects.create(name='Article editors')
        group.permissions.add(grant)
        for changes in [{'is_superuser': 'on'}, {'user_permissions': [grant.pk]}, {'groups': [group.pk]}]:
            with self.subTest(changes=changes):
                form = SafeUserChangeForm(self.popup_data(User.objects.get(pk=self.reader.pk), **changes),
                                          instance=User.objects.get(pk=self.reader.pk))
                form.actor = self.manager
                self.assertFalse(form.is_valid())
                self.assertIn('que usted tiene', str(form.non_field_errors()))

    def test_native_popup_preserves_safe_add_change_permission_and_group_flows(self):
        grant = Permission.objects.get(codename='view_user', content_type__app_label='auth')
        group = Group.objects.create(name='User viewers')
        group.permissions.add(grant)
        response = self.client.get(f'/admin/auth/user/{self.reader.pk}/change/?_popup=1')
        form = response.context['adminform'].form
        self.assertIn(grant, form.fields['user_permissions'].queryset)
        self.assertIn(group, form.fields['groups'].queryset)
        response = self.client.post(f'/admin/auth/user/{self.reader.pk}/change/?_popup=1',
                                    self.popup_data(self.reader, groups=[group.pk], user_permissions=[grant.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-popup-response')
        self.reader.refresh_from_db()
        self.assertEqual(self.reader.first_name, 'Updated')
        self.assertEqual(list(self.reader.groups.all()), [group])
        response = self.client.post('/admin/auth/user/add/?_popup=1', {
            'username': 'related-reader', 'usable_password': 'true', '_popup': '1',
            'password1': 'Unusual-Cobalt-8824!', 'password2': 'Unusual-Cobalt-8824!',
            'is_superuser': 'on', 'is_staff': 'on', 'user_permissions': [grant.pk], 'groups': [group.pk]})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-popup-response')
        user = User.objects.get(username='related-reader')
        self.assertTrue(user.check_password('Unusual-Cobalt-8824!'))
        self.assertFalse(user.is_superuser or user.is_staff or user.user_permissions.exists() or user.groups.exists())

    def test_superuser_targets_block_directory_popup_password_and_delete(self):
        page = self.client.get(f'/admin/auth/user/?user={self.root.pk}')
        self.assertFalse(page.context['can_edit'])
        self.assertEqual(self.client.post(f'/admin/auth/user/?user={self.root.pk}', {
            'username': self.root.username, 'role': 'reader', 'is_active': 'on'}).status_code, 403)
        for suffix in ['change/?_popup=1', 'password/', 'delete/']:
            response = self.client.post(f'/admin/auth/user/{self.root.pk}/{suffix}', {
                **self.popup_data(self.root), 'password1': 'Reset-Example-8824!',
                'password2': 'Reset-Example-8824!', 'post': 'yes'})
            self.assertEqual(response.status_code, 403)

    def test_higher_non_superuser_targets_allow_safe_demotion_but_block_credential_takeover(self):
        dormant = User.objects.create_user('dormant', is_active=False)
        group = Group.objects.create(name='Dormant article editors')
        group.permissions.set(permissions(['athena.change_article']))
        dormant.groups.add(group)
        for user in [self.editor, dormant]:
            with self.subTest(user=user.username):
                page = self.client.get(f'/admin/auth/user/?user={user.pk}')
                self.assertTrue(page.context['can_edit'])
                self.assertFalse(page.context['can_reset_password'])
                self.assertNotContains(page, f'/admin/auth/user/{user.pk}/password/')
                self.assertEqual(self.client.post(f'/admin/auth/user/{user.pk}/password/', {
                    'password1': 'Reset-Example-8824!', 'password2': 'Reset-Example-8824!',
                    'usable_password': 'true'}).status_code, 403)
                response = self.client.post('/admin/athena/apikey/add/', self.key_data(user))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['adminform'].form.errors)
                self.assertFalse(ApiKey.objects.exists())
                response = self.client.post(f'/admin/auth/user/?user={user.pk}', {
                    'username': user.username, 'role': 'reader', 'is_active': 'on',
                    'edits': ['articles', 'downloads', 'users']})
                self.assertEqual(response.status_code, 302)
                user.refresh_from_db()
                self.assertFalse(user.is_staff or user.is_superuser or user.user_permissions.exists() or user.groups.exists())
                page = self.client.get(f'/admin/auth/user/?user={user.pk}')
                self.assertTrue(page.context['can_reset_password'])
                self.assertContains(page, f'/admin/auth/user/{user.pk}/password/')
                self.assertEqual(self.client.post(f'/admin/auth/user/{user.pk}/password/', {
                    'password1': 'Reset-Example-8824!', 'password2': 'Reset-Example-8824!',
                    'usable_password': 'true'}).status_code, 302)

    def test_higher_native_popup_target_keeps_readonly_password_and_permits_safe_removal(self):
        password = self.editor.password
        response = self.client.post(f'/admin/auth/user/{self.editor.pk}/change/?_popup=1',
                                    self.popup_data(self.editor, password='Attacker-controlled-password'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-popup-response')
        self.editor.refresh_from_db()
        self.assertEqual(self.editor.password, password)
        self.assertEqual(self.editor.first_name, 'Updated')
        self.assertFalse(self.editor.user_permissions.exists() or self.editor.is_staff)
        self.assertEqual(self.client.post(f'/admin/auth/user/{self.editor.pk}/delete/', {'post': 'yes'}).status_code, 302)
        self.assertFalse(User.objects.filter(pk=self.editor.pk).exists())

    def test_password_reset_and_directory_permitted_grants_still_work(self):
        response = self.client.post(f'/admin/auth/user/{self.reader.pk}/password/', {
            'password1': 'Reset-Example-8824!', 'password2': 'Reset-Example-8824!', 'usable_password': 'true'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.get(pk=self.reader.pk).check_password('Reset-Example-8824!'))
        response = self.client.post(f'/admin/auth/user/?user={self.reader.pk}', {
            'username': self.reader.username, 'role': 'admin', 'edits': ['users'], 'is_active': 'on'})
        self.assertEqual(response.status_code, 302)
        self.reader.refresh_from_db()
        self.assertTrue(self.reader.is_staff and self.reader.has_perm('auth.change_user'))
        self.assertFalse(self.reader.is_superuser or self.reader.has_perm('athena.change_article'))

    def test_non_superuser_holding_all_edit_areas_cannot_mint_superusers(self):
        self.manager.user_permissions.set(Permission.objects.all())
        form = DirectoryUserForm({'username': 'reader', 'role': 'admin', 'edits': ['articles', 'downloads', 'users'],
                                  'is_active': 'on'}, actor=self.manager, instance=self.reader)
        self.assertFalse(form.is_valid())
        self.assertIn('que usted tiene', str(form.non_field_errors()))

    def test_group_user_manager_can_keep_own_management_access(self):
        group = Group.objects.create(name='User managers')
        group.permissions.set(permissions(['auth.change_user']))
        self.manager.user_permissions.clear()
        self.manager.groups.add(group)
        self.client.force_login(User.objects.get(pk=self.manager.pk))
        response = self.client.post(f'/admin/auth/user/{self.manager.pk}/change/?_popup=1',
                                    self.popup_data(self.manager, is_staff='on', groups=[group.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-popup-response')
        self.assertTrue(User.objects.get(pk=self.manager.pk).has_perm('auth.change_user'))

    def test_directory_group_manager_shows_and_can_grant_held_areas(self):
        group = Group.objects.create(name='Directory user managers')
        group.permissions.set(permissions(ADMIN_VIEW + EDIT_AREAS['users']))
        self.manager.user_permissions.clear()
        self.manager.groups.add(group)
        self.client.force_login(User.objects.get(pk=self.manager.pk))
        self.assertEqual(held_areas(self.manager), {'users'})
        response = self.client.get(f'/admin/auth/user/?user={self.manager.pk}')
        self.assertEqual(response.context['form']['edits'].value(), ['users'])
        response = self.client.post(f'/admin/auth/user/?user={self.reader.pk}', {
            'username': self.reader.username, 'role': 'admin', 'edits': ['users'], 'is_active': 'on'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.get(pk=self.reader.pk).has_perm('auth.change_user'))

    def test_directory_reader_demotion_removes_inherited_edit_grants_from_existing_key(self):
        group = Group.objects.create(name='Inherited article editors')
        group.permissions.set(permissions(EDIT_AREAS['articles']))
        self.editor.groups.add(group)
        _, raw = self.issue_key(self.editor, 'articles')
        headers = {'HTTP_AUTHORIZATION': 'Bearer ' + raw}
        self.assertTrue(self.client.get('/api/v1/me/', **headers).json()['can']['write_articles'])
        self.client.force_login(self.root)
        response = self.client.post(f'/admin/auth/user/?user={self.editor.pk}', {
            'username': self.editor.username, 'role': 'reader', 'is_active': 'on'})
        self.assertEqual(response.status_code, 302)
        self.editor.refresh_from_db()
        self.assertFalse(self.editor.is_staff or self.editor.is_superuser or self.editor.groups.exists())
        self.assertFalse(self.editor.user_permissions.exists())
        self.assertFalse(self.client.get('/api/v1/me/', **headers).json()['can']['write_articles'])
        response = self.client.patch('/api/v1/articles/guide/', json.dumps({'body': '# Forbidden'}),
                                     content_type='application/json',
                                     HTTP_IF_MATCH=f'"{self.article.updated_at.isoformat()}"', **headers)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Article.objects.get(pk=self.article.pk).body, self.article.body)

    def test_directory_area_removal_keeps_allowed_groups_and_revokes_existing_key_grants(self):
        articles = Group.objects.create(name='Article writers')
        articles.permissions.set(permissions(EDIT_AREAS['articles']))
        downloads = Group.objects.create(name='Download managers')
        downloads.permissions.set(permissions(EDIT_AREAS['downloads']))
        self.editor.user_permissions.clear()
        self.editor.groups.add(articles, downloads)
        self.assertEqual(held_areas(self.editor), {'articles', 'downloads'})
        _, raw = self.issue_key(self.editor, 'articles')
        headers = {'HTTP_AUTHORIZATION': 'Bearer ' + raw}
        self.client.force_login(self.root)
        response = self.client.post(f'/admin/auth/user/?user={self.editor.pk}', {
            'username': self.editor.username, 'role': 'admin', 'edits': ['downloads'], 'is_active': 'on'})
        self.assertEqual(response.status_code, 302)
        self.editor.refresh_from_db()
        self.assertTrue(self.editor.is_staff)
        self.assertFalse(self.editor.is_superuser)
        self.assertEqual(list(self.editor.groups.all()), [downloads])
        self.assertEqual(held_areas(self.editor), {'downloads'})
        current = self.client.get('/api/v1/me/', **headers).json()['can']
        self.assertFalse(current['write_articles'])
        self.assertTrue(current['manage_downloads'])
        response = self.client.patch('/api/v1/articles/guide/', json.dumps({'body': '# Forbidden'}),
                                     content_type='application/json',
                                     HTTP_IF_MATCH=f'"{self.article.updated_at.isoformat()}"', **headers)
        self.assertEqual(response.status_code, 403)
        response = self.client.post(f'/admin/auth/user/{self.editor.pk}/change/?_popup=1',
                                    self.popup_data(self.editor, is_staff='on', groups=[downloads.pk],
                                                    user_permissions=list(self.editor.user_permissions.values_list('pk', flat=True))))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-popup-response')
        self.assertEqual(list(User.objects.get(pk=self.editor.pk).groups.all()), [downloads])

    def test_api_superuser_demotion_removes_inherited_grants_from_existing_key(self):
        target = User.objects.create_superuser('second-root', password='Other-Example-8824!')
        group = Group.objects.create(name='Inherited editors and download managers')
        group.permissions.set(permissions(EDIT_AREAS['articles'] + EDIT_AREAS['downloads']))
        target.groups.add(group)
        target.user_permissions.set(permissions(['auth.change_user']))
        _, target_raw = self.issue_key(target)
        headers = {'HTTP_AUTHORIZATION': 'Bearer ' + target_raw}
        self.assertTrue(self.client.get('/api/v1/me/', **headers).json()['can']['write_articles'])
        _, root_raw = self.issue_key(self.root)
        response = self.client.patch(f'/api/v1/users/{target.pk}/', json.dumps({'admin': False}),
                                     content_type='application/json', HTTP_AUTHORIZATION='Bearer ' + root_raw)
        self.assertEqual(response.status_code, 200)
        target.refresh_from_db()
        self.assertFalse(target.is_staff or target.is_superuser or target.groups.exists())
        self.assertFalse(target.user_permissions.exists())
        capability = self.client.get('/api/v1/me/', **headers).json()['can']
        self.assertFalse(capability['write_articles'] or capability['manage_downloads'] or capability['manage_users'])
        response = self.client.patch('/api/v1/articles/guide/', json.dumps({'body': '# Forbidden'}),
                                     content_type='application/json',
                                     HTTP_IF_MATCH=f'"{self.article.updated_at.isoformat()}"', **headers)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.post('/api/v1/downloads/', {}, **headers).status_code, 403)

    def test_stale_admin_save_keeps_submitted_text_and_cannot_restore_publication(self):
        self.client.force_login(self.root)
        path = f'/admin/athena/article/{self.article.pk}/change/'
        revision = self.client.get(path).context['adminform'].form['loaded_revision'].value()
        stale = self.article_data(loaded_revision=revision, title='Old title edit', body='# Unsaved body\nKeep this text')
        response = self.client.post(path, self.article_data(body='# Reviewed body', published='', is_public='False'))
        self.assertEqual(response.status_code, 302)
        response = self.client.post(path, stale)
        self.assertContains(response, 'El artículo cambió desde que abrió esta página.')
        self.assertContains(response, '# Unsaved body\nKeep this text')
        form = response.context['adminform'].form
        self.assertEqual(form['body'].value(), stale['body'])
        self.assertEqual(form['loaded_revision'].value(), revision)
        self.article.refresh_from_db()
        self.assertEqual(self.article.body, '# Reviewed body')
        self.assertEqual(self.article.title, 'Guide')
        self.assertFalse(self.article.published or self.article.is_public)

    def test_missing_and_invalid_admin_revision_cannot_save(self):
        self.client.force_login(self.root)
        path = f'/admin/athena/article/{self.article.pk}/change/'
        for revision in ['', 'not-a-revision', 'x' * 51]:
            with self.subTest(revision=revision):
                response = self.client.post(path, self.article_data(body='Must not save', loaded_revision=revision))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['adminform'].form.errors)
                self.assertEqual(Article.objects.get(pk=self.article.pk).body, self.article.body)

    def test_admin_create_import_pdf_and_current_revision_save_still_work(self):
        self.client.force_login(self.root)
        data = self.article_data(title='Created', slug='created', body='', loaded_revision='',
                                 markdown_file=SimpleUploadedFile('created.md', b'# Imported\nContent'),
                                 pdf_file=SimpleUploadedFile('created.pdf', b'%PDF-1.7\n%%EOF'))
        self.assertEqual(self.client.post('/admin/athena/article/add/', data).status_code, 302)
        created = Article.objects.get(slug='created')
        self.assertEqual(created.body, '# Imported\nContent')
        self.assertEqual(created.pdf_name, 'created.pdf')
        path = f'/admin/athena/article/{self.article.pk}/change/'
        form = self.client.get(path).context['adminform'].form
        response = self.client.post(path, self.article_data(loaded_revision=form['loaded_revision'].value(),
                                                           body='# Revised', remove_pdf='on'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Article.objects.get(pk=self.article.pk).body, '# Revised')

    def test_api_article_form_does_not_require_browser_revision(self):
        _, raw = self.issue_key(self.root, 'articles')
        headers = {'HTTP_AUTHORIZATION': 'Bearer ' + raw}
        path = f'/api/v1/articles/{self.article.slug}/'
        current = self.client.get(path, **headers)
        response = self.client.patch(path, json.dumps({'body': '# API save'}), content_type='application/json',
                                     HTTP_IF_MATCH=current['ETag'], **headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Article.objects.get(pk=self.article.pk).body, '# API save')


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False,
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class LoginNormalizationRegressionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser('login-user', password='Login-Example-8824!')

    def test_whitespace_and_nfkc_aliases_share_counter_across_both_login_forms(self):
        variants = ['login-user', ' login-user', 'login-user\t', '\tlogin-user ', 'ｌｏｇｉｎ-user']
        for first in ['/accounts/login/', '/admin/login/']:
            with self.subTest(first=first):
                LoginAttempt.objects.all().delete()
                for index, username in enumerate(variants):
                    path = first if index % 2 == 0 else '/admin/login/' if first == '/accounts/login/' else '/accounts/login/'
                    response = Client().post(path, {'username': username, 'password': 'wrong'},
                                             REMOTE_ADDR=f'192.0.2.{index + 1}')
                    self.assertEqual(response.status_code, 200)
                account_key = hashlib.sha256(b'user:login-user').hexdigest()
                self.assertTrue(LoginAttempt.objects.get(pk=account_key).locked_until)
                for path in ['/accounts/login/', '/admin/login/']:
                    response = Client().post(path, {'username': ' login-user ', 'password': 'Login-Example-8824!'},
                                             REMOTE_ADDR='192.0.2.99')
                    self.assertEqual(response.status_code, 429)
                    self.assertEqual(response['Retry-After'], '900')

    def test_normalized_success_clears_same_account_counter(self):
        for path in ['/accounts/login/', '/admin/login/']:
            with self.subTest(path=path):
                LoginAttempt.objects.all().delete()
                Client().post(path, {'username': 'ｌｏｇｉｎ-user ', 'password': 'wrong'})
                response = Client().post(path, {'username': '\tlogin-user ', 'password': 'Login-Example-8824!'})
                self.assertEqual(response.status_code, 302)
                attempt = LoginAttempt.objects.get(pk=hashlib.sha256(b'user:login-user').hexdigest())
                self.assertEqual(attempt.count, 0)
                self.assertIsNone(attempt.locked_until)

    def test_long_and_invalid_usernames_still_count_toward_ip_limit(self):
        for path in ['/accounts/login/', '/admin/login/']:
            with self.subTest(path=path):
                LoginAttempt.objects.all().delete()
                for username in ['', 'a' * 151, 'ｌ' * 151, 'bad\x00name', 'missing']:
                    response = Client().post(path, {'username': username, 'password': 'wrong'})
                    self.assertEqual(response.status_code, 200)
                response = Client().post(path, {'username': 'login-user', 'password': 'Login-Example-8824!'})
                self.assertEqual(response.status_code, 429)
