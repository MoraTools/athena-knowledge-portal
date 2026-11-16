/* The article's share image: upload through the article image endpoint, keep its id in the hidden field. */
(function () {
  const MIN_WIDTH = 600;
  const MIN_HEIGHT = 315;
  const MAX_BYTES = 5 * 1000 * 1000;
  const TYPES = ['image/png', 'image/jpeg'];

  function attachShareImage(box) {
    const input = box.querySelector('input[type="hidden"]');
    const body = document.querySelector('#id_body[data-image-upload-url]');
    const form = input && input.form;
    if (!input || !body || !form) return;
    let preview = box.querySelector('.share-image-preview');
    if (!preview) {
      preview = document.createElement('img');
      preview.className = 'share-image-preview';
      preview.alt = 'Imagen para compartir';
      input.after(preview);
    }
    const tools = document.createElement('div');
    tools.className = 'share-image-tools';
    const choose = document.createElement('button');
    choose.type = 'button';
    choose.className = 'button';
    // The field label points at the hidden input; the button is the control it names.
    choose.id = input.id;
    input.removeAttribute('id');
    choose.setAttribute('aria-describedby', `${choose.id}_helptext`);
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'button';
    remove.textContent = 'Quitar imagen';
    const picker = document.createElement('input');
    picker.type = 'file';
    picker.accept = TYPES.join(',');
    picker.hidden = true;
    const status = document.createElement('span');
    status.className = 'share-image-status';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    tools.append(choose, remove, picker, status);
    box.append(tools);
    let uploading = false;

    function message(text, error = false) {
      status.textContent = text;
      status.classList.toggle('share-image-status--error', error);
    }
    function show() {
      choose.textContent = input.value ? 'Cambiar imagen' : 'Elegir imagen';
      remove.hidden = !input.value;
      preview.hidden = !input.value;
    }
    function set(id, url) {
      input.value = id;
      if (url) preview.src = url; else preview.removeAttribute('src');
      show();
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }

    async function upload(file) {
      if (!TYPES.includes(file.type) || file.size > MAX_BYTES) {
        throw new Error('Use una imagen PNG o JPEG de hasta 5 MB.');
      }
      const data = new FormData();
      data.append('file', file);
      if (body.dataset.imageArticleId) data.append('article_id', body.dataset.imageArticleId);
      const csrf = form.querySelector('input[name="csrfmiddlewaretoken"]');
      let response;
      for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
          response = await fetch(body.dataset.imageUploadUrl, {
            method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrf ? csrf.value : '' }, body: data
          });
        } catch (_) {
          throw new Error('No se pudo conectar con el servidor. Intente de nuevo.');
        }
        if (response.status !== 503 || attempt === 2) break;
        const seconds = Number(response.headers.get('Retry-After')) || 2;
        await new Promise(resolve => setTimeout(resolve, Math.min(10, Math.max(1, seconds)) * 1000));
      }
      let result;
      try { result = await response.json(); } catch (_) {
        throw new Error('El servidor no respondió. Intente de nuevo.');
      }
      if (!response.ok) throw new Error(typeof result.error === 'string' ? result.error : 'No se pudo subir la imagen. Intente de nuevo.');
      if (!/^[0-9a-f-]{36}$/.test(result.id || '') || !/^\/article-images\/[0-9a-f-]{36}\/$/.test(result.url || '')) {
        throw new Error('La respuesta del servidor no es válida. Intente de nuevo.');
      }
      if (!TYPES.includes(result.content_type) || result.size > MAX_BYTES) {
        throw new Error('Use una imagen PNG o JPEG de hasta 5 MB.');
      }
      if (result.width < MIN_WIDTH || result.height < MIN_HEIGHT) {
        throw new Error('La imagen es demasiado pequeña. Use al menos 600 × 315 píxeles (mejor 1200 × 630).');
      }
      return result;
    }

    choose.addEventListener('click', () => picker.click());
    picker.addEventListener('change', async () => {
      const file = picker.files && picker.files[0];
      picker.value = '';
      if (!file) return;
      uploading = true;
      choose.disabled = remove.disabled = true;
      message('Subiendo la imagen…');
      try {
        const result = await upload(file);
        set(result.id, result.url);
        message('Imagen lista. Guarde el artículo para usarla en el enlace.');
      } catch (error) {
        message(error.message, true);  // The field keeps its previous value.
      } finally {
        uploading = false;
        choose.disabled = remove.disabled = false;
        choose.focus();
      }
    });
    remove.addEventListener('click', () => {
      set('', '');
      message('Se quitará al guardar. El enlace dejará de mostrar la vista previa.');
      choose.focus();
    });
    form.addEventListener('submit', event => {
      if (!uploading) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      message('Espere a que termine la subida antes de guardar.', true);
    }, true);
    show();
  }

  function attachCopy(button) {
    const field = document.getElementById('share-link-url');
    const status = button.parentElement.querySelector('.share-link-status');
    if (!field || !navigator.clipboard) return;  // Without the clipboard API the field stays selectable.
    button.hidden = false;
    button.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(field.value);
        status.textContent = 'Enlace copiado.';
      } catch (_) {
        field.select();
        status.textContent = 'No se pudo copiar. El enlace está seleccionado: cópielo con Ctrl+C.';
      }
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-share-image]').forEach(attachShareImage);
    document.querySelectorAll('[data-copy-share-link]').forEach(attachCopy);
  });
})();
