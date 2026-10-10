from datetime import date
from types import SimpleNamespace

from django.test import SimpleTestCase

from .views import article_body, search_entry


class ReaderRegressionTests(SimpleTestCase):
    def article(self, body, **changes):
        fields = dict(title='Guide', slug='guide', kind='guide', summary='Summary', author='Author',
                      date=date(2026, 10, 9), tags=['RPA'], body=body, pdf_name='', published=True)
        return SimpleNamespace(**(fields | changes))

    def test_search_uses_actual_h1_and_ignores_fenced_headings(self):
        article = self.article('# Intro\n\n```sh\n## Deploy\n```\n\n## Guide\n\nneedle\n\n'
                               '~~~\n## Guide\n~~~\n\n## Deploy\n\nreal section')
        entry = search_entry(article)
        self.assertEqual([heading['raw'] for heading in entry['headings']], ['Intro', 'Guide', 'Deploy'])
        self.assertEqual([heading['level'] for heading in entry['headings']], [1, 2, 2])
        self.assertIn('needle', entry['headings'][1]['text'])
        self.assertEqual(entry['route'], '#/content/guide')
        self.assertEqual(entry['tags'], ['RPA'])

    def test_search_preserves_inline_source_setext_and_duplicate_order(self):
        article = self.article('## **Deploy** and [help](https://example.test)\n\nFirst\n\n'
                               'Deploy\n------\n\nSecond\n\n> ### Deploy\n>\n> Third\n\n'
                               '#### Deploy\n\nFourth\n\n## Deploy\n\nFifth')
        headings = search_entry(article)['headings']
        self.assertEqual([heading['level'] for heading in headings], [1, 2, 2, 3, 4, 2])
        self.assertEqual(headings[1]['raw'], '**Deploy** and [help](https://example.test)')
        self.assertEqual(headings[1]['title'], 'Deploy and help')
        self.assertEqual(headings[2]['text'], 'Second')

    def test_original_pdf_has_its_own_marker_after_citations(self):
        article = self.article('# Guide\n\n[External](https://example.test/other.pdf)\n\n'
                               '[Other article](/pdf/other.pdf)', pdf_name='original.pdf')
        body = article_body(article)
        self.assertIn('[External](https://example.test/other.pdf)', body)
        self.assertIn('[Other article](/pdf/other.pdf)', body)
        self.assertTrue(body.endswith('<p class="article-pdf"><a href="/pdf/guide.pdf">Abrir PDF original</a></p>\n'))
        self.assertEqual(search_entry(article)['pdf'], '/pdf/guide.pdf')
