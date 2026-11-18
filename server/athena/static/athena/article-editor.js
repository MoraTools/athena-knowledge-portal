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
    // The editor page has its own h1; the preview title keeps the reader's look as a level 2 heading.
    renderer.heading = function (token) {
      const html = marked.Renderer.prototype.heading.call(this, token);
      return token.depth === 1 ? html.replace('<h1', '<h1 aria-level="2"') : html;
    };
    return DOMPurify.sanitize(marked.parse(body, { renderer, gfm: true, breaks: false }), {
      FORBID_TAGS: ['style', 'iframe', 'script', 'object', 'embed', 'form', 'input', 'select', 'option', 'textarea', 'button', 'fieldset', 'label', 'dialog', 'svg', 'math'],
      FORBID_ATTR: ['style', 'id', 'name', 'form', 'class', 'autofocus', 'contenteditable', 'tabindex', 'autoplay'],
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
    let validating = false;
    let timer;
    const ACCESS_LABELS = { public: 'Público', account: 'Con cuenta', restricted: 'Restringido' };
    const KIND_LABELS = { guide: 'Guía', page: 'Página', tool: 'Herramienta', announcement: 'Anuncio', release: 'Versión' };
    const saveState = document.getElementById('desk-save-state');
    let shownState = null;
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
      tab.addEventListener('click', () => { showDetailTab(tab); tab.focus(); });  // Safari does not focus clicked buttons.
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
      opener = button && overflow.contains(button) ? overflow.querySelector('summary') : button || document.querySelector('.desk-details');
      overflow.open = false;
      if (!dialog.open) {
        snapshot = { dirty, saveText: saveState?.textContent, controls: [...dialog.querySelectorAll('input, select, textarea')].map(control => [control, readControl(control)]) };
        dialog.showModal();
      }
      target?.focus();
      // A field that cannot take focus leaves it on the selected tab, never on the dialog's first tab.
      if (!target || document.activeElement !== target) detailTabs.find(tab => tab.getAttribute('aria-selected') === 'true').focus();
      target?.scrollIntoView({ block: 'center' });
    }
    // ×, Cancelar and Esc put back every control of the dialog as it was at open; Aplicar keeps the changes.
    // Django's SelectFilter2 keeps its lists in SelectBox.cache, so those are put back from there.
    let snapshot = null;
    function readControl(control) {
      const box = window.SelectBox?.cache?.[control.id];
      if (box) return JSON.stringify(box);
      if (control.type === 'checkbox' || control.type === 'radio') return control.checked;
      if (control.type === 'file') return control.files;
      if (control.multiple) return JSON.stringify([...control.options].map(option => option.selected));
      return control.value;
    }
    function writeControl(control, state) {
      if (window.SelectBox?.cache?.[control.id]) {
        window.SelectBox.cache[control.id] = JSON.parse(state);
        window.SelectBox.redisplay(control.id);
      } else if (control.type === 'checkbox' || control.type === 'radio') control.checked = state;
      else if (control.type === 'file') control.files = state;
      else if (control.multiple) JSON.parse(state).forEach((selected, index) => { control.options[index].selected = selected; });
      else control.value = state;
    }
    function discardDetails() {
      for (const [control, state] of snapshot?.controls ?? []) {
        if (readControl(control) === state) continue;
        writeControl(control, state);
        // The form hooks (kind, preview, chips) and each widget's own listeners see the old value.
        control.dispatchEvent(new Event('input', { bubbles: true }));
        control.dispatchEvent(new Event('change', { bubbles: true }));
      }
      if (snapshot && !snapshot.dirty) {
        dirty = false;
        if (saveState) saveState.textContent = snapshot.saveText;
      }
    }
    dialog.close();
    document.querySelectorAll('[data-open-details]').forEach(button => button.addEventListener('click', () => openDetails(button, button.dataset.detailFocus)));
    document.querySelector('[data-close-details]').addEventListener('click', () => { if (!importing) dialog.close(); });
    dialog.querySelectorAll('[data-cancel-details]').forEach(button => button.addEventListener('click', () => {
      if (importing) return;
      discardDetails();
      dialog.close();
    }));
    dialog.addEventListener('cancel', event => { if (importing) event.preventDefault(); else discardDetails(); });
    dialog.addEventListener('close', () => opener?.focus());
    document.addEventListener('keydown', event => { if (event.key === 'Escape') overflow.open = false; });
    document.addEventListener('click', event => { if (!overflow.contains(event.target)) overflow.open = false; });

    // HTML articles: the server renders unsaved source into the reader's sandboxed frame. A srcdoc or blob
    // frame would inherit the admin CSP and block the article's own scripts.
    const htmlPreviewUrl = source.dataset.htmlPreviewUrl;
    const previewStatus = document.getElementById('desk-preview-status');
    const sourceHeading = document.getElementById('desk-source-heading');
    const format = () => value('format', form.dataset.format || 'markdown');
    let htmlFrame = null;
    const htmlHead = document.createElement('div');
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
      // The reader shows the title and the meta line above an HTML article's frame.
      const heading = document.createElement('h1');
      heading.setAttribute('aria-level', '2');  // As the Markdown preview: the editor page has its own h1.
      heading.textContent = title.value;
      htmlHead.replaceChildren(heading, metaLine());
      if (fresh) {
        preview.classList.add('desk-preview-content--html');
        preview.replaceChildren(htmlHead, htmlFrame);
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

    // The same chips as the server (admin.state_chips): a draft is for editors only until it is published.
    function stateChips(published, access) {
      const label = ACCESS_LABELS[access] || ACCESS_LABELS.account;
      const pill = (tone, text) => `<span class="pill${tone}">${text}</span>`;
      if (published) return pill('', 'Publicado') + pill(access === 'restricted' ? ' warn' : '', label);
      return pill(' warn', 'Borrador') + pill(' off', 'Solo editores') + `<span class="state-next"><span>al publicar:</span> <span>${label}</span></span>`;
    }

    // Placement tags (models.PLACEMENT_TAGS) place an article on the home; like the reader, the preview shows no chip for them.
    const placementTags = (form.dataset.placementTags || '').split(',').filter(Boolean);
    // The reader's meta line (type · author · Actualizado date, then the topic tags on their own row) from the Detalles fields.
    function metaLine() {
      const meta = document.createElement('p');
      meta.className = 'article-meta';
      const span = (text, lang) => Object.assign(document.createElement('span'), { textContent: text }, lang ? { lang } : {});
      meta.append(span(KIND_LABELS[value('kind', form.dataset.articleKind)] || KIND_LABELS.guide));
      if (value('author').trim()) meta.append('·', span(value('author').trim(), 'es'));
      const day = form.dataset.updated || new Date().toLocaleDateString('sv');  // Unsaved: the date it gets on save.
      const time = document.createElement('time');
      time.dateTime = day;
      time.textContent = new Intl.DateTimeFormat(document.documentElement.lang || 'es', { dateStyle: 'medium' }).format(new Date(day + 'T12:00:00'));
      meta.append('·', span('Actualizado'), time);
      const tags = value('tags').split(',').map(tag => tag.trim()).filter(tag => tag && !placementTags.includes(tag.toLowerCase()));
      if (tags.length) {
        const list = span('', 'es');
        list.className = 'article-meta__tags';
        list.append(...tags.map(tag => span(tag)));
        meta.append(list);
      }
      return meta;
    }

    function updatePreview() {
      const published = checked('published', form.dataset.published === 'true');
      const access = value('access', form.dataset.access || 'account');
      const state = stateChips(published, access);
      // The user list matters only for "Usuarios seleccionados"; without JavaScript it stays visible.
      const picker = document.querySelector('.form-row.field-allowed_users');
      if (picker) picker.hidden = access !== 'restricted' && !picker.classList.contains('errors');
      if (state !== shownState) {  // Only on a change, so the translated chips are not rebuilt on every key.
        shownState = state;
        document.getElementById('desk-state').innerHTML = state;
        document.getElementById('desk-details-state').innerHTML = state;
      }
      document.getElementById('desk-count').textContent = `${words().split(/\s+/).filter(Boolean).length} palabras`;
      const pdf = form.elements.namedItem('pdf_file')?.files?.[0];
      const pdfName = pdf?.name || (checked('remove_pdf') ? '' : form.dataset.pdfName);
      const label = format() === 'html' ? 'HTML' : 'Markdown';
      sourceHeading.textContent = label;
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
      preview.querySelector('h1')?.after(metaLine());
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
    function markDirty() {
      if (!dirty && saveState) saveState.textContent = 'Cambios sin guardar';
      dirty = true;
    }
    // The title is one line: Enter does nothing and pasted line breaks become spaces.
    title.addEventListener('keydown', event => { if (event.key === 'Enter') event.preventDefault(); });
    form.addEventListener('input', event => {
      if (event.target === title && /[\r\n]/.test(title.value)) title.value = title.value.replace(/\s*[\r\n]+\s*/g, ' ');
      markDirty();
      clearTimeout(timer);
      timer = setTimeout(updatePreview, 120);
    });
    // The tag list completes the tag after the last comma: each option holds the tags typed so far plus one more,
    // and a tag already typed is not offered again.
    const tagsField = document.getElementById('id_tags');
    const tagOptions = tagsField?.list ? [...tagsField.list.options].map(option => [option, option.value]) : [];
    tagsField?.addEventListener('input', () => {
      const typed = tagsField.value.split(',').slice(0, -1).map(tag => tag.trim()).filter(Boolean);
      const prefix = typed.length ? `${typed.join(', ')}, ` : '';
      const used = new Set(typed.map(tag => tag.toLowerCase()));
      for (const [option, tag] of tagOptions) {
        option.value = prefix + tag;
        option.disabled = used.has(tag.toLowerCase());
      }
    });
    function showToolFields() {
      const kind = value('kind', form.dataset.articleKind);
      toolFields.open = kind === 'tool' || Boolean(toolFields.querySelector('.errors'));
      const release = document.getElementById('desk-release');
      if (release) release.hidden = kind !== 'release';
    }
    showToolFields();
    form.addEventListener('change', event => {
      markDirty();
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

    // Only this form's own submit check routes errors: widgets such as Django's SelectFilter2 call checkValidity()
    // on load and on every change, and those invalid events must not open Detalles.
    form.addEventListener('invalid', event => {
      if (!validating) return;
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
      validating = true;
      const valid = form.checkValidity();
      if (!valid) form.reportValidity();
      validating = false;
      if (!valid) {
        event.preventDefault();
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
