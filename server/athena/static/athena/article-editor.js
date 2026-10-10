/* Native Markdown source and a sanitized reader preview. No rich-text editor state. */
(() => {
  const escapeHTML = value => String(value).replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
  function readerHref(href, slug) {
    const explicit = /^\/?#\//.test(href);
    if (!explicit && /^(?:[a-z][a-z0-9+.-]*:|\/\/|#)/i.test(href)) return href;
    const url = new URL(explicit ? href.replace(/^\/?#/, '') : href, new URL(`/content/${slug || 'new'}`, location.origin));
    const reader = explicit || !/^\/(?:pdf|downloads|article-images)\//.test(url.pathname)
      && (url.pathname.endsWith('.md') || url.pathname.startsWith('/content/') && !/\.[^/]+$/.test(url.pathname)
        || /^\/(?:guides|tools|updates|search|account|api)\/?$/.test(url.pathname));
    if (!reader) return url.href;
    if (url.hash) {
      let id = url.hash.slice(1);
      try { id = decodeURIComponent(id); } catch { /* Keep malformed escapes without stopping the preview. */ }
      url.searchParams.set('id', id);
    }
    return `/#${url.pathname.replace(/\.md$/, '')}${url.search}`;
  }
  function renderMarkdown(body, { title = '', published = false, pdfName = '', slug = '' } = {}) {
    if (!/^\s*#\s+/.test(body)) body = `# ${escapeHTML(title)}\n\n${body}`;
    if (!published) body = '> **Borrador.** Solo visible para editores.\n\n' + body;
    if (pdfName && slug) body += `\n\n[Abrir PDF original](/pdf/${slug}.pdf)\n`;
    const renderer = new marked.Renderer();
    // Static task states preserve Markdown meaning without form controls in the preview.
    renderer.checkbox = ({ checked }) => checked ? '[x] ' : '[ ] ';
    renderer.image = function (token) {
      let href = token.href;
      if (!/^(?:[a-z][a-z0-9+.-]*:|\/\/|#)/i.test(href)) {
        href = new URL(href, new URL(`/content/${slug || 'new'}`, location.origin)).href;
      }
      return marked.Renderer.prototype.image.call(this, { ...token, href });
    };
    renderer.link = function (token) {
      return marked.Renderer.prototype.link.call(this, { ...token, href: readerHref(token.href, slug) });
    };
    return DOMPurify.sanitize(marked.parse(body, { renderer, gfm: true, breaks: false }), {
      FORBID_TAGS: ['style', 'iframe', 'script', 'object', 'embed', 'form', 'input', 'select', 'option', 'textarea', 'button', 'fieldset', 'label', 'dialog', 'svg', 'math'],
      FORBID_ATTR: ['style', 'id', 'name', 'form', 'class', 'autofocus', 'contenteditable', 'tabindex'],
      ALLOW_DATA_ATTR: false
    });
  }
  window.athenaRenderMarkdown = renderMarkdown;

  document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('article_form');
    const source = document.getElementById('id_body');
    const title = document.getElementById('id_title');
    const preview = document.getElementById('desk-preview-content');
    const dialog = document.getElementById('article-details');
    if (!form || !source || !title || !preview || !dialog) return;
    const narrow = matchMedia('(max-width: 1024px)');
    function compactRail() {
      if (narrow.matches) return;
      document.documentElement.dataset.rail = 'compact';
      const toggle = document.querySelector('.rail-toggle');
      if (toggle) {
        toggle.setAttribute('aria-label', 'Expandir la navegación');
        toggle.setAttribute('aria-expanded', 'false');
        toggle.querySelector('.rail-label').textContent = 'Expandir';
      }
    }
    compactRail();
    narrow.addEventListener('change', compactRail);
    const imageFooter = document.getElementById('desk-image-footer');
    const imageTools = document.querySelector('.article-image-tools');
    const imageHelp = document.getElementById('id_body_helptext');
    if (imageTools) imageFooter.append(imageTools);
    if (imageHelp) imageFooter.append(imageHelp);
    const overflow = document.querySelector('.desk-overflow');
    let opener = null;
    let dirty = false;
    let submitting = false;
    let importing = false;
    let timer;
    const value = (name, fallback = '') => form.elements.namedItem(name)?.value ?? fallback;
    const checked = (name, fallback = false) => form.elements.namedItem(name)?.checked ?? fallback;

    function openDetails(button, field) {
      opener = button && overflow.contains(button) ? overflow.querySelector('summary') : button || document.querySelector('[data-open-details]');
      overflow.open = false;
      if (!dialog.open) dialog.showModal();
      if (field) {
        const target = document.getElementById(field);
        target?.focus();
        target?.scrollIntoView({ block: 'center' });
      }
    }
    dialog.close();
    document.querySelectorAll('[data-open-details]').forEach(button => button.addEventListener('click', () => openDetails(button, button.dataset.detailFocus)));
    document.querySelector('[data-close-details]').addEventListener('click', () => { if (!importing) dialog.close(); });
    dialog.addEventListener('cancel', event => { if (importing) event.preventDefault(); });
    dialog.addEventListener('close', () => opener?.focus());
    document.addEventListener('keydown', event => { if (event.key === 'Escape') overflow.open = false; });
    document.addEventListener('click', event => { if (!overflow.contains(event.target)) overflow.open = false; });

    function updatePreview() {
      const published = checked('published', form.dataset.published === 'true');
      const access = value('is_public', form.dataset.public === 'true' ? 'True' : 'False') === 'True';
      document.getElementById('desk-state').textContent = `${published ? 'Publicado' : 'Borrador'} · ${access ? 'Público' : 'Con cuenta'}`;
      document.getElementById('desk-count').textContent = `${source.value.trim().split(/\s+/).filter(Boolean).length} palabras`;
      const pdf = form.elements.namedItem('pdf_file')?.files?.[0];
      const pdfName = pdf?.name || (checked('remove_pdf') ? '' : form.dataset.pdfName);
      if (!window.marked || !window.DOMPurify) {
        preview.textContent = 'No se pudo cargar la vista previa. Puede editar y guardar Markdown.';
        return;
      }
      preview.innerHTML = renderMarkdown(source.value, { title: title.value, published, pdfName, slug: value('slug', form.dataset.articleSlug) });
      preview.querySelectorAll('a').forEach(link => {
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        const href = link.getAttribute('href');
        if (href) link.href = readerHref(href, value('slug', form.dataset.articleSlug));
        if (href?.startsWith('#') && !href.startsWith('#/')) {
          link.removeAttribute('target');
          link.addEventListener('click', event => event.preventDefault());
        }
      });
    }
    form.addEventListener('input', () => {
      dirty = true;
      clearTimeout(timer);
      timer = setTimeout(updatePreview, 120);
    });
    form.addEventListener('change', () => { dirty = true; updatePreview(); });

    const markdownFile = document.getElementById('id_markdown_file');
    markdownFile?.addEventListener('change', async () => {
      const file = markdownFile.files[0];
      if (!file) return;
      const help = document.getElementById('id_markdown_file_helptext');
      help.setAttribute('role', 'status');
      help.setAttribute('aria-live', 'polite');
      if (source.hasAttribute('aria-busy')) {
        markdownFile.value = '';
        help.textContent = 'Espere a que terminen las imágenes antes de importar Markdown.';
        return;
      }
      importing = true;
      markdownFile.disabled = true;
      const readOnly = source.readOnly;
      source.readOnly = true;
      const imageButton = document.querySelector('.article-image-tools button');
      if (imageButton) imageButton.disabled = true;
      help.textContent = 'Leyendo Markdown. Espere para guardar.';
      try {
        if (!file.name.toLowerCase().endsWith('.md') || file.size > 1024 * 1024) throw new Error('Use un archivo .md de hasta 1 MiB.');
        const body = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer());
        source.value = body.replace(/^<!--\s*athena:.*?-->\s*/s, '');
        // Consume the import now, so Django does not replace subsequent edits on save.
        markdownFile.value = '';
        help.textContent = `${file.name} importado. Puede editar el Markdown antes de guardar.`;
        source.dispatchEvent(new Event('input', { bubbles: true }));
        updatePreview();
      } catch (error) {
        help.textContent = error instanceof TypeError ? 'No se pudo leer el archivo. Use Markdown UTF-8.' : error.message;
        // Keep rejected files selected so server validation also reports the error.
      } finally {
        importing = false;
        markdownFile.disabled = false;
        source.readOnly = readOnly;
        if (imageButton) imageButton.disabled = false;
      }
    });
    source.addEventListener('paste', event => {
      if (importing) { event.preventDefault(); event.stopImmediatePropagation(); }
    }, true);

    form.addEventListener('invalid', event => {
      if (dialog.contains(event.target)) openDetails(null, event.target.id);
    }, true);
    form.addEventListener('submit', event => {
      if (importing) {
        event.preventDefault();
        openDetails(null, 'id_markdown_file');
        return;
      }
      if (!form.checkValidity()) {
        event.preventDefault();
        form.reportValidity();
        return;
      }
      if (!event.defaultPrevented && !source.hasAttribute('aria-busy')) submitting = true;
    });
    window.addEventListener('beforeunload', event => {
      if (dirty && !submitting) { event.preventDefault(); event.returnValue = ''; }
    });

    const workspace = document.querySelector('.desk-workspace');
    const tabs = [...document.querySelectorAll('[data-pane]')];
    function showPane(tab) {
      workspace.dataset.activePane = tab.dataset.pane;
      tabs.forEach(button => {
        button.setAttribute('aria-selected', String(button === tab));
        button.tabIndex = button === tab ? 0 : -1;
      });
    }
    tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => showPane(tab));
      tab.addEventListener('keydown', event => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        event.preventDefault();
        const next = tabs[event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + 1) % tabs.length];
        showPane(next); next.focus();
      });
    });
    updatePreview();
    const detailsError = dialog.querySelector('.errors input, .errors select, .errors textarea');
    if (detailsError) openDetails(null, detailsError.id);
  });
})();
