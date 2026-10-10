/* Native Markdown textarea: each pending image has its own replaceable marker. */
(function () {
  function attachArticleImages(textarea) {
    const form = textarea.form;
    const url = textarea.dataset.imageUploadUrl;
    if (!form || !url || textarea.disabled || textarea.readOnly) return;
    const editor = document.createElement('div');
    editor.className = 'article-image-editor';
    textarea.before(editor);
    editor.append(textarea);
    const tools = document.createElement('div');
    tools.className = 'article-image-tools';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'button';
    button.textContent = 'Insertar imagen';
    const picker = document.createElement('input');
    picker.type = 'file';
    picker.accept = 'image/png,image/jpeg,image/webp,image/gif';
    picker.multiple = true;
    picker.hidden = true;
    const status = document.createElement('span');
    status.id = 'article-image-status';
    status.className = 'article-image-status';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    tools.append(button, picker, status);
    editor.append(tools);
    textarea.setAttribute('aria-describedby', [textarea.getAttribute('aria-describedby'), status.id].filter(Boolean).join(' '));

    let pending = 0;
    let errorText = '';
    const queue = [];
    let uploading = false;
    const disabled = new Map();
    function message(text, error = false) {
      status.textContent = text;
      status.classList.toggle('article-image-status--error', error);
    }
    function update() {
      if (pending) {
        for (const submit of form.querySelectorAll('input[type="submit"],button[type="submit"]')) {
          if (!disabled.has(submit)) disabled.set(submit, submit.disabled);
          submit.disabled = true;
        }
        textarea.setAttribute('aria-busy', 'true');
        message(`Subiendo ${pending} ${pending === 1 ? 'imagen' : 'imágenes'}. Puede seguir escribiendo; espere para guardar.`);
      } else {
        for (const [submit, wasDisabled] of disabled) submit.disabled = wasDisabled;
        disabled.clear();
        textarea.removeAttribute('aria-busy');
        message(errorText || 'Imagen insertada. Puede guardar el artículo.', Boolean(errorText));
      }
    }

    function replace(start, end, value) {
      const selection = [textarea.selectionStart, textarea.selectionEnd, textarea.selectionDirection];
      const scroll = textarea.scrollTop;
      const delta = value.length - (end - start);
      // Keep the user's current selection over the same text when an earlier upload completes.
      const move = (position) => position < start ? position : position >= end ? position + delta : start + value.length;
      textarea.setRangeText(value, start, end, 'preserve');
      textarea.setSelectionRange(move(selection[0]), move(selection[1]), selection[2]);
      textarea.scrollTop = scroll;
      textarea.dispatchEvent(new Event('input', { bubbles: true }));
    }

    const allowedTypes = ['image/png', 'image/jpeg', 'image/webp', 'image/gif'];
    // Some clipboard files have no MIME type. The server still checks their actual bytes.
    const knownFile = file => (!file.type || file.type === 'application/octet-stream') && /\.(png|jpe?g|webp|gif)$/i.test(file.name || '');
    const imageFile = file => file && (file.type.startsWith('image/') || knownFile(file));

    async function upload(file, marker) {
      try {
        if (!(allowedTypes.includes(file.type) || knownFile(file)) || file.size > 10 * 1024 * 1024) {
          throw new Error('Use PNG, JPEG, WebP o GIF de hasta 10 MiB.');
        }
        const data = new FormData();
        data.append('file', file);
        if (textarea.dataset.imageArticleId) data.append('article_id', textarea.dataset.imageArticleId);
        const csrf = form.querySelector('input[name="csrfmiddlewaretoken"]');
        let response;
        for (let attempt = 0; attempt < 3; attempt += 1) {
          try {
            response = await fetch(url, {
              method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrf ? csrf.value : '' }, body: data
            });
          } catch (_) {
            throw new Error('No se pudo conectar con el servidor. Vuelva a insertar la imagen.');
          }
          if (response.status !== 503 || attempt === 2) break;
          const seconds = Number(response.headers.get('Retry-After')) || 2;
          await new Promise(resolve => setTimeout(resolve, Math.min(10, Math.max(1, seconds)) * 1000));
        }
        let result;
        try { result = await response.json(); } catch (_) {
          throw new Error('El servidor no respondió. Vuelva a insertar la imagen.');
        }
        if (!response.ok) throw new Error(typeof result.error === 'string' ? result.error : 'No se pudo subir la imagen. Intente de nuevo.');
        if (!/^\/article-images\/[0-9a-f-]{36}\/$/.test(result.url || '')) throw new Error('La dirección de la imagen no es válida. Intente de nuevo.');
        const position = textarea.value.indexOf(marker);
        if (position >= 0) replace(position, position + marker.length, `![Imagen](${result.url})`);
      } catch (error) {
        const position = textarea.value.indexOf(marker);
        if (position >= 0) replace(position, position + marker.length, '');
        errorText += `${errorText ? ' ' : ''}${file.name || 'Imagen'}: ${error.message || 'No se pudo subir la imagen.'} Su texto se conservó.`;
      } finally {
        pending -= 1;
        update();
      }
    }

    async function drain() {
      if (uploading) return;
      uploading = true;
      try {
        while (queue.length) {
          const job = queue.shift();
          await upload(job.file, job.marker);
        }
      } finally {
        uploading = false;
      }
    }

    function insert(files) {
      if (!files.length) return;
      if (!pending) errorText = '';
      const jobs = files.map(file => ({ file, marker: `<!-- athena-image-upload:${crypto.randomUUID()} -->` }));
      const start = textarea.selectionStart;
      // Images are inserted before selected text, so upload failure cannot remove the user's text.
      replace(start, start, jobs.map(job => job.marker).join('\n'));
      pending += jobs.length;
      update();
      queue.push(...jobs);
      drain();
    }

    textarea.addEventListener('paste', event => {
      const clipboard = event.clipboardData;
      let images = Array.from(clipboard?.files || []).filter(imageFile);
      if (!images.length) images = Array.from(clipboard?.items || [])
        .filter(item => item.kind === 'file').map(item => item.getAsFile()).filter(imageFile);
      if (!images.length) return;
      event.preventDefault();
      insert(images);
    });
    button.addEventListener('click', () => picker.click());
    picker.addEventListener('change', () => {
      const files = Array.from(picker.files || []);
      picker.value = '';
      textarea.focus();
      insert(files);
    });
    form.addEventListener('submit', event => {
      if (pending || textarea.value.includes('<!-- athena-image-upload:')) {
        event.preventDefault();
        event.stopImmediatePropagation();
        message(pending ? 'Espere a que termine la subida antes de guardar.' : 'Quite el marcador de imagen incompleto antes de guardar.', true);
      }
    }, true);
    window.addEventListener('beforeunload', event => {
      if (pending) { event.preventDefault(); event.returnValue = ''; }
    });
    return { insert };
  }

  document.addEventListener('DOMContentLoaded', () => {
    const textarea = document.querySelector('#id_body[data-image-upload-url]');
    if (textarea) attachArticleImages(textarea);
  });
})();
