import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../server/athena/static/athena/article-images.js', import.meta.url), 'utf8');
class Element {
  constructor() {
    Object.assign(this, { children: [], listeners: {}, attributes: {}, disabled: false,
      classList: { toggle() {} }, textContent: '' });
  }
  append(...items) { this.children.push(...items); }
  before(item) { this.wrapper = item; }
  setAttribute(name, value) { this.attributes[name] = value; }
  getAttribute(name) { return this.attributes[name] || null; }
  removeAttribute(name) { delete this.attributes[name]; }
  addEventListener(type, handler) { (this.listeners[type] ||= []).push(handler); }
  dispatchEvent(event) { for (const handler of this.listeners[event.type] || []) handler(event); }
}

function setup() {
  const requests = [], timers = [], handlers = {}, submit = new Element();
  let active = 0, peak = 0, serial = 0;
  const form = new Element();
  form.querySelectorAll = () => [submit];
  form.querySelector = () => ({ value: 'csrf-token' });
  const textarea = new Element();
  Object.assign(textarea, { form, dataset: { imageUploadUrl: '/article-images/upload/' },
    value: 'Before SELECTED After', selectionStart: 7, selectionEnd: 15,
    selectionDirection: 'backward', scrollTop: 83,
    setRangeText(value, start, end) { this.value = this.value.slice(0, start) + value + this.value.slice(end); },
    setSelectionRange(start, end, direction) {
      this.selectionStart = start; this.selectionEnd = end; this.selectionDirection = direction;
    }
  });
  vm.runInNewContext(source, {
    document: { createElement: () => new Element(), querySelector: () => textarea,
      addEventListener(type, callback) { handlers[type] = callback; } },
    window: { addEventListener(type, callback) { handlers[type] = callback; } },
    crypto: { randomUUID: () => `00000000-0000-4000-8000-${String(++serial).padStart(12, '0')}` },
    Event: class { constructor(type) { this.type = type; } },
    FormData: class { constructor() { this.fields = new Map(); } append(name, value) { this.fields.set(name, value); } },
    setTimeout(callback, delay) { timers.push({ callback, delay }); },
    fetch(url, options) {
      active += 1;
      peak = Math.max(peak, active);
      return new Promise((resolve, reject) => requests.push({ url, options,
        resolve(value) { active -= 1; resolve(value); }, reject(error) { active -= 1; reject(error); } }));
    }
  });
  handlers.DOMContentLoaded();
  return { textarea, form, submit, requests, timers, handlers,
    status: textarea.wrapper.children[1].children[2], peak: () => peak };
}

const file = name => ({ name, type: 'image/png', size: 123 });
const url = n => `/article-images/00000000-0000-4000-8000-${String(n).padStart(12, '0')}/`;
const flush = () => new Promise(setImmediate);
function paste(state, files) {
  state.textarea.dispatchEvent({ type: 'paste', clipboardData: { files }, preventDefault() {} });
}
function saveBlocked(state) {
  let blocked = false;
  state.form.dispatchEvent({ type: 'submit', preventDefault() { blocked = true; }, stopImmediatePropagation() {} });
  return blocked;
}
async function respond(request, status = 201, data = { url: url(1) }, retry = '2') {
  request.resolve({ status, ok: status < 400, headers: { get: () => retry }, json: async () => data });
  await flush();
}

// Separate paste calls join the same queue, while selection and unsaved text survive each result.
{
  const state = setup();
  paste(state, [file('one.png'), file('two.png')]);
  paste(state, [file('three.png')]);
  assert.equal(state.requests.length, 1);
  assert.equal(saveBlocked(state), true);
  assert.equal(state.submit.disabled, true);
  state.textarea.value += ' unsaved';
  const selection = state.textarea.value.indexOf('SELECTED');
  state.textarea.setSelectionRange(selection, selection + 8, 'backward');
  for (let n = 1; n <= 3; n += 1) {
    assert.equal(state.requests.length, n);
    assert.equal(state.requests[n - 1].options.body.fields.get('file').name, ['one.png', 'two.png', 'three.png'][n - 1]);
    await respond(state.requests[n - 1], 201, { url: url(n) });
    assert.equal(state.textarea.value.slice(state.textarea.selectionStart, state.textarea.selectionEnd), 'SELECTED');
    assert.equal(state.textarea.selectionDirection, 'backward');
    assert.equal(state.textarea.scrollTop, 83);
    assert.equal(saveBlocked(state), n < 3);
  }
  assert.equal(state.textarea.value, `Before ![Imagen](${url(1)})\n![Imagen](${url(2)})![Imagen](${url(3)})SELECTED After unsaved`);
  assert.equal(state.peak(), 1);
  assert.equal(state.submit.disabled, false);
}

// Busy retries keep the first job's marker and never start a later job at the same time.
{
  const state = setup();
  paste(state, [file('busy.png'), file('later.png')]);
  const body = state.textarea.value;
  await respond(state.requests[0], 503, { error: 'Busy' });
  assert.equal(state.requests.length, 1);
  assert.equal(state.textarea.value, body);
  assert.equal(saveBlocked(state), true);
  assert.equal(state.timers[0].delay, 2000);
  state.timers.shift().callback();
  await flush();
  assert.equal(state.requests.length, 2);
  assert.equal(state.requests[1].options.body, state.requests[0].options.body);
  await respond(state.requests[1]);
  assert.equal(state.requests.length, 3);
  assert.equal(state.requests[2].options.body.fields.get('file').name, 'later.png');
  await respond(state.requests[2], 201, { url: url(2) });
  assert.equal(state.peak(), 1);
  assert.equal(saveBlocked(state), false);
}

// Three busy attempts exhaust the bound, report that file, and continue every later job.
{
  const state = setup();
  paste(state, [file('busy.png'), file('broken.png'), file('good.png')]);
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await respond(state.requests[attempt], 503, { error: 'El servidor está ocupado.' }, '99');
    if (attempt < 2) {
      assert.equal(state.timers[0].delay, 10000);
      state.timers.shift().callback();
      await flush();
    }
  }
  assert.equal(state.timers.length, 0);
  assert.equal(state.requests.length, 4);
  assert.equal(state.requests[3].options.body.fields.get('file').name, 'broken.png');
  state.requests[3].reject(new TypeError('Failed to fetch'));
  await flush();
  assert.equal(state.requests.length, 5);
  assert.equal(state.requests[4].options.body.fields.get('file').name, 'good.png');
  await respond(state.requests[4]);
  assert.match(state.status.textContent, /busy\.png: El servidor está ocupado/);
  assert.match(state.status.textContent, /broken\.png: No se pudo conectar/);
  assert.equal(state.textarea.value, `Before \n\n![Imagen](${url(1)})SELECTED After`);
  assert.equal(state.textarea.value.includes('athena-image-upload:'), false);
  assert.equal(state.peak(), 1);
  assert.equal(saveBlocked(state), false);
  assert.equal(state.submit.disabled, false);
}

console.log('Image queue serial peak: 1. Cross-paste order, selection, text, bounded busy retries and failed-job continuation passed.');
