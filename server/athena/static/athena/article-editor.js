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
    const ACCESS_LABELS = { public: 'Público', account: 'Con cuenta', restricted: 'Restringido' };
    const value = (name, fallback = '') => form.elements.namedItem(name)?.value ?? fallback;
    const checked = (name, fallback = false) => form.elements.namedItem(name)?.checked ?? fallback;
    const detailTabs = [...dialog.querySelectorAll('[data-detail-tab]')];
    const detailPanels = [...dialog.querySelectorAll('.desk-detail-panel')];
    const toolFields = document.getElementById('desk-tool-fields');

    function showDetailTab(tab) {
      detailTabs.forEach(button => {
        button.setAttribute('aria-selected', String(button === tab));
        button.tabIndex = button === tab ? 0 : -1;
      });
      detailPanels.forEach(panel => { panel.hidden = panel.id !== tab.getAttribute('aria-controls'); });
    }
    detailTabs.forEach((tab, index) => {
      tab.addEventListener('click', () => showDetailTab(tab));
      tab.addEventListener('keydown', event => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        event.preventDefault();
        const next = detailTabs[event.key === 'Home' ? 0 : event.key === 'End' ? detailTabs.length - 1
          : (index + (event.key === 'ArrowLeft' ? -1 : 1) + detailTabs.length) % detailTabs.length];
        showDetailTab(next);
        next.focus();
      });
    });
    showDetailTab(detailTabs[0]);
    dialog.dataset.enhanced = 'true';

    function openDetails(button, field) {
      const target = field && document.getElementById(field);
      const panel = target?.closest('.desk-detail-panel');
      if (panel) showDetailTab(detailTabs.find(tab => tab.getAttribute('aria-controls') === panel.id));
      if (target && toolFields.contains(target)) toolFields.open = true;
      opener = button && overflow.contains(button) ? overflow.querySelector('summary') : button || document.querySelector('[data-open-details]');
      overflow.open = false;
      if (!dialog.open) dialog.showModal();
      (target || detailTabs.find(tab => tab.getAttribute('aria-selected') === 'true')).focus();
      target?.scrollIntoView({ block: 'center' });
    }
    dialog.close();
    document.querySelectorAll('[data-open-details]').forEach(button => button.addEventListener('click', () => openDetails(button, button.dataset.detailFocus)));
    document.querySelector('[data-close-details]').addEventListener('click', () => { if (!importing) dialog.close(); });
    dialog.addEventListener('cancel', event => { if (importing) event.preventDefault(); });
    dialog.addEventListener('close', () => opener?.focus());
    document.addEventListener('keydown', event => { if (event.key === 'Escape') overflow.open = false; });
    document.addEventListener('click', event => { if (!overflow.contains(event.target)) overflow.open = false; });

    // HTML articles: the server renders unsaved source into the reader's sandboxed frame. A srcdoc or blob
    // frame would inherit the admin CSP and block the article's own scripts.
    const htmlPreviewUrl = source.dataset.htmlPreviewUrl;
    const previewStatus = document.getElementById('desk-preview-status');
    const sourceHeading = document.getElementById('desk-source-heading');
    const sourceTab = document.querySelector('[data-pane="source"]');
    const format = () => value('format', form.dataset.format || 'markdown');
    let htmlFrame = null;
    let htmlForm = null;
    let htmlTimer;
    let heightTimer;
    let viewportPending = false;
    const sendFrame = (type, data) => htmlFrame?.contentWindow?.postMessage({ type, value: data }, '*');
    function frameViewport() {
      if (!htmlFrame?.isConnected) return;
      const frame = htmlFrame.getBoundingClientRect();
      const pane = preview.getBoundingClientRect();
      const top = Math.max(0, Math.max(pane.top, 0) - frame.top);
      const bottom = Math.min(frame.height, Math.min(pane.bottom, innerHeight) - frame.top);
      sendFrame('athena:viewport', { top, height: Math.max(0, bottom - top) || innerHeight });
    }
    function queueViewport() {
      if (viewportPending) return;
      viewportPending = true;
      requestAnimationFrame(() => { viewportPending = false; frameViewport(); });
    }
    function syncFrame() {
      sendFrame('athena:theme', document.documentElement.dataset.theme);
      sendFrame('athena:lang', document.documentElement.lang);
      frameViewport();
    }
    const frameQuery = () => new URLSearchParams({ theme: document.documentElement.dataset.theme || 'light', lang: document.documentElement.lang || 'es' });
    function loadHtmlPreview() {
      clearTimeout(heightTimer);
      heightTimer = setTimeout(() => { previewStatus.textContent = 'La vista previa no respondió. Revise el HTML y vuelva a escribir.'; }, 4000);
      if (!htmlPreviewUrl) {  // A view-only page shows the saved article.
        htmlFrame.src = `/article-html/${encodeURIComponent(form.dataset.articleSlug)}/?${frameQuery()}`;
        return;
      }
      if (!htmlForm) {
        htmlForm = document.createElement('form');
        htmlForm.method = 'post';
        htmlForm.target = htmlFrame.name;
        htmlForm.hidden = true;
        const csrf = document.createElement('input');
        csrf.type = 'hidden';
        csrf.name = 'csrfmiddlewaretoken';
        csrf.value = form.querySelector('input[name="csrfmiddlewaretoken"]')?.value || '';
        const body = document.createElement('textarea');
        body.name = 'body';
        htmlForm.append(csrf, body);
        document.body.append(htmlForm);
      }
      htmlForm.action = `${htmlPreviewUrl}?${frameQuery()}`;
      htmlForm.elements.body.value = source.value;
      htmlForm.submit();
    }
    function showHtmlPreview() {
      if (!htmlFrame) {
        htmlFrame = document.createElement('iframe');
        htmlFrame.name = 'desk-html-preview';
        htmlFrame.className = 'desk-html-frame';
        htmlFrame.title = 'Vista previa del artículo HTML';
        htmlFrame.setAttribute('sandbox', 'allow-scripts allow-popups allow-popups-to-escape-sandbox');
        addEventListener('message', event => {
          if (!htmlFrame.isConnected || event.source !== htmlFrame.contentWindow || !event.data || typeof event.data !== 'object') return;
          const { type, value: data } = event.data;
          if (type === 'athena:height' && Number.isFinite(data) && data >= 0) {
            clearTimeout(heightTimer);
            previewStatus.textContent = '';
            htmlFrame.style.height = `${Math.min(Math.ceil(data), 100000)}px`;
            queueViewport();
          } else if (type === 'athena:ready' || type === 'athena:viewport-request') {
            syncFrame();
          } else if (type === 'athena:scroll' && Number.isFinite(data)) {
            preview.scrollTop += htmlFrame.getBoundingClientRect().top - preview.getBoundingClientRect().top + data;
          }
        });
        preview.addEventListener('scroll', queueViewport, { passive: true });
        addEventListener('resize', queueViewport);
        document.addEventListener('suite:theme', () => sendFrame('athena:theme', document.documentElement.dataset.theme));
        document.addEventListener('suite:lang', () => sendFrame('athena:lang', document.documentElement.lang));
      }
      const fresh = !htmlFrame.isConnected;
      if (fresh) {
        preview.classList.add('desk-preview-content--html');
        preview.replaceChildren(htmlFrame);
      }
      clearTimeout(htmlTimer);
      // Typing waits for a pause; a switch to HTML or a view-only page loads at once.
      if (fresh || !htmlPreviewUrl) loadHtmlPreview();
      else htmlTimer = setTimeout(loadHtmlPreview, 300);
    }

    // HTML counts the readable text, as search does; DOMParser documents run no scripts and load nothing.
    function words() {
      if (format() !== 'html') return source.value.trim();
      const doc = new DOMParser().parseFromString(source.value, 'text/html');
      doc.querySelectorAll('script, style, template, noscript').forEach(node => node.remove());
      return (doc.body?.textContent || '').trim();
    }

    function updatePreview() {
      const published = checked('published', form.dataset.published === 'true');
      const access = value('access', form.dataset.access || 'account');
      const state = `${published ? 'Publicado' : 'Borrador'} · ${ACCESS_LABELS[access] || 'Con cuenta'}`;
      // The user list matters only for "Usuarios seleccionados"; without JavaScript it stays visible.
      const picker = document.querySelector('.form-row.field-allowed_users');
      if (picker) picker.hidden = access !== 'restricted' && !picker.classList.contains('errors');
      document.getElementById('desk-state').textContent = state;
      document.getElementById('desk-details-state').textContent = state;
      document.getElementById('desk-count').textContent = `${words().split(/\s+/).filter(Boolean).length} palabras`;
      const pdf = form.elements.namedItem('pdf_file')?.files?.[0];
      const pdfName = pdf?.name || (checked('remove_pdf') ? '' : form.dataset.pdfName);
      const label = format() === 'html' ? 'HTML' : 'Markdown';
      sourceHeading.textContent = label;
      if (sourceTab) sourceTab.textContent = label;
      if (format() === 'html') {
        showHtmlPreview();
        return;
      }
      clearTimeout(htmlTimer);
      clearTimeout(heightTimer);
      previewStatus.textContent = '';
      preview.classList.remove('desk-preview-content--html');
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
    function showToolFields() { toolFields.open = value('kind', form.dataset.articleKind) === 'tool' || Boolean(toolFields.querySelector('.errors')); }
    showToolFields();
    form.addEventListener('change', event => {
      dirty = true;
      if (event.target.name === 'kind') showToolFields();
      updatePreview();
    });

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
      const firstInvalid = form.querySelector('input:invalid, select:invalid, textarea:invalid');
      if (event.target !== firstInvalid) { event.preventDefault(); return; }
      if (dialog.contains(event.target)) openDetails(null, event.target.id);
      else {
        if (dialog.open) { opener = null; dialog.close(); }
        if (event.target === source) showPane(tabs[0]);
        event.target.focus();
      }
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
