import assert from 'node:assert/strict';
import { readFileSync, readdirSync, existsSync, mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawn } from 'node:child_process';
import vm from 'node:vm';

const root = new URL('../', import.meta.url);
const read = (path) => readFileSync(new URL(path, root), 'utf8');
const bootSource = read('src/assets/boot.js');
const context = vm.createContext({});
vm.runInContext(bootSource, context);
const boot = context.SuiteBoot;
for (const [stored, dark, expected] of [[null, true, 'dark'], [null, false, 'light'], ['light', true, 'light'], ['dark', false, 'dark'], ['invalid', true, 'dark']]) {
  assert.equal(boot.resolveTheme(stored, dark), expected);
}
for (const [stored, languages, expected] of [[null, ['fr', 'en-US', 'es'], 'en'], [null, ['es-PE', 'en'], 'es'], ['en', ['es'], 'en'], [null, ['fr'], 'es'], ['invalid', ['es-MX'], 'es']]) {
  assert.equal(boot.resolveLang(stored, languages), expected);
}
assert.equal(boot.storedValueAfterToggle('dark', 'dark'), null);
assert.equal(boot.storedValueAfterToggle('en', 'es'), 'en');
for (const path of ['src/index.html', 'src/request-access.html', 'server/athena/templates/base.html', 'server/athena/templates/admin/base_site.html']) {
  const source = read(path);
  assert(source.indexOf('/assets/boot.js') < source.indexOf('rel="stylesheet"'), path + ': boot must precede styles');
  assert.equal((source.match(/data-suite-toggle=/g) || []).length, 2, path + ': exactly two toggles');
  assert(!/<script(?![^>]*\bsrc=)[^>]*>\s*\S/.test(source), path + ': external scripts only');
}
// The admin head: boot.js and the suite tokens replace Django's dark_mode.css and theme.js; the suite scripts end the body.
const adminBase = read('server/athena/templates/admin/base_site.html');
assert(/\{% block dark-mode-vars %\}<script src="\/assets\/boot\.js"><\/script>.*suite-tokens\.css.*\{% endblock %\}/.test(adminBase), 'admin: boot.js and tokens in the first head block');
assert(/\{% block extrabody %\}.*suite-i18n\.js.*suite\.js.*\{% endblock %\}/.test(adminBase), 'admin: suite scripts at the end of the body');
// Colour literals: none in the shared rail and the admin stylesheets (they read the suite tokens).
for (const path of ['src/assets/rail.css', 'server/athena/static/athena/admin.css', 'server/athena/static/athena/admin-directory.css', 'server/athena/static/athena/admin-sidebar.css', 'server/athena/static/athena/article-editor.css']) {
  const declarations = [...read(path).replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/\{([^{}]*)\}/g)].map((match) => match[1]).join(';');
  assert(!/#[\da-f]{3,8}\b|\b(?:rgba?|hsla?)\(|:\s*(?:black|white)\b/i.test(declarations), path + ': colour literal outside the token blocks');
  assert(!/Archivo|Courier|Sigurd/.test(read(path)), path + ': old font');
}
const tokenSource = read('src/assets/suite-tokens.css');
const nonTokenSource = tokenSource.replace(/(?:@media[^{}]*\{)?[^{}]*\{[^{}]*--(?:rail|bg):[^{}]*\}/g, '');
assert(!/#[\da-f]{3,8}\b|\brgba?\(/i.test(nonTokenSource), 'Color literals belong only to theme token blocks');
assert(!/data-variant|URLSearchParams|document\.cookie/.test(bootSource + read('src/assets/suite.js')), 'No preview state or cookies');
console.log('Suite preferences, browser fallbacks, reset rules, head ordering, CSP and token boundaries passed.');

const urlIndex = process.argv.indexOf('--url');
if (urlIndex === -1) process.exit(0);
const origin = new URL(process.argv[urlIndex + 1]).origin;
const sessionIndex = process.argv.indexOf('--session');
const session = sessionIndex === -1 ? '' : process.argv[sessionIndex + 1];
const shotsIndex = process.argv.indexOf('--screenshots');
const shots = shotsIndex === -1 ? null : process.argv[shotsIndex + 1];
const profile = mkdtempSync(join(tmpdir(), 'athena-theme-chrome-'));
const chrome = spawn(process.env.CHROME || 'chromium', ['--headless', '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--remote-debugging-port=0', '--remote-debugging-address=127.0.0.1', '--lang=es', '--user-data-dir=' + profile, 'about:blank'], { stdio: 'ignore' });
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let socket;
try {
  let port;
  for (let i = 0; i < 100; i++) {
    try { port = readFileSync(join(profile, 'DevToolsActivePort'), 'utf8').split('\n')[0]; break; } catch { await delay(100); }
  }
  assert(port, 'Chromium must start');
  const tabs = await fetch(`http://127.0.0.1:${port}/json/list`).then((response) => response.json());
  socket = new WebSocket(tabs.find((tab) => tab.type === 'page').webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  let serial = 0;
  const pending = new Map();
  const errors = [];
  socket.onmessage = ({ data }) => {
    const message = JSON.parse(data);
    if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text + ': ' + (message.params.exceptionDetails.exception?.description || ''));
    if (!message.id) return;
    const item = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) item.reject(new Error(JSON.stringify(message.error)));
    else item.resolve(message.result);
  };
  function send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = ++serial;
      pending.set(id, { resolve, reject });
      socket.send(JSON.stringify({ id, method, params }));
    });
  }
  async function evaluate(expression) {
    const response = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
    if (response.exceptionDetails) throw new Error(response.exceptionDetails.exception?.description || response.exceptionDetails.text);
    return response.result.value;
  }
  async function ready(path) {
    for (let i = 0; i < 100; i++) {
      const done = await evaluate(`document.readyState === 'complete' && !!window.AthenaI18n && ${path.startsWith('/#') ? "!!document.querySelector('.markdown-section h1')" : 'true'}`);
      if (done) { await evaluate('document.fonts.ready'); await delay(150); return; }
      await delay(100);
    }
    throw new Error('Page did not render: ' + path);
  }
  await send('Page.enable');
  await send('Runtime.enable');
  await send('Network.enable');
  let init;
  async function navigate(path, theme = 'dark', lang = 'en', width = 1440) {
    if (init) await send('Page.removeScriptToEvaluateOnNewDocument', { identifier: init });
    // Admin views reject unknown query parameters: leave the page first, then load the plain URL.
    const admin = path.startsWith('/admin/');
    if (admin) await send('Page.navigate', { url: 'about:blank' });
    const marker = String(Date.now()) + '-' + serial;
    init = (await send('Page.addScriptToEvaluateOnNewDocument', { source: `window.__suiteTestNavigation=${JSON.stringify(marker)};localStorage.setItem('suite.athena.theme',${JSON.stringify(theme)});localStorage.setItem('suite.athena.lang',${JSON.stringify(lang)});localStorage.removeItem('athena.rail');` })).identifier;
    await send('Emulation.setDeviceMetricsOverride', { width, height: width === 390 ? 844 : 900, deviceScaleFactor: 1, mobile: width === 390 });
    await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: 'light' }] });
    const target = new URL(origin + path);
    if (!admin) target.searchParams.set('suite-test', marker);
    await send('Page.navigate', { url: target.href });
    for (let i = 0; i < 100; i++) {
      if (await evaluate(`window.__suiteTestNavigation === ${JSON.stringify(marker)} && location.origin === ${JSON.stringify(origin)}`)) break;
      await delay(50);
    }
    await ready(path);
  }
  const routes = [
    ['home', '/#/'], ['guides', '/#/guides'], ['article', '/#/content/domxpath'], ['search', '/#/search?q=recorder'],
    ['tools', '/#/tools'], ['updates', '/#/updates'], ['signin', '/accounts/login/'], ['admin-signin', '/admin/login/']
  ];
  const issues = [];
  const djangoStrings = new Map();
  // Django's own Spanish catalogs: built-in admin strings stay Spanish (manager's decision) and are listed apart.
  const catalog = (() => {
    const django = join(new URL('.venv/lib/', root).pathname, readdirSync(new URL('.venv/lib/', root)).find((name) => name.startsWith('python')) || '', 'site-packages/django');
    const files = ['conf/locale/es/LC_MESSAGES/django.po', 'contrib/admin/locale/es/LC_MESSAGES/django.po', 'contrib/admin/locale/es/LC_MESSAGES/djangojs.po', 'contrib/auth/locale/es/LC_MESSAGES/django.po'].map((file) => join(django, file));
    const sources = [];
    for (const file of files.filter(existsSync)) {
      const unquote = (block) => [...block.matchAll(/"((?:[^"\\]|\\.)*)"/g)].map((match) => JSON.parse('"' + match[1] + '"')).join('');
      for (const entry of readFileSync(file, 'utf8').split(/\n\n+/)) {
        const id = entry.match(/^msgid ((?:".*"\n?)+)/m);
        for (const match of entry.matchAll(/^msgstr(?:\[\d\])? ((?:".*"\n?)+)/gm)) {
          const text = unquote(match[1]).trim();
          if (!text || id && unquote(id[1]).trim() === text || text.replace(/%(?:\([^)]+\))?[sd]/g, '').replace(/[^\p{L}]/gu, '').length < 2) continue;
          sources.push('^' + text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/%(?:\\\([^)]+\\\)|\([^)]+\))?[sd]/g, '.+?') + ':?$');
        }
      }
    }
    return sources;
  })();
  assert(catalog.length > 100, 'Django Spanish catalogs must load');
  const spanish = await (async () => {
    await navigate('/#/');
    return evaluate('Object.keys(AthenaI18n.dictionary).filter(x => AthenaI18n.dictionary[x] !== x)');
  })();
  const dictionarySet = JSON.stringify(spanish);
  const catalogSource = JSON.stringify(catalog);
  async function audit(name) {
    const [result, builtIn] = await evaluate(`(() => {
      const spanish = new Set(${dictionarySet});
      const django = ${catalogSource}.map((source) => new RegExp(source, 'iu'));
      const found = new Set();
      const builtIn = new Set();
      const languagePattern = /[¿¡]|\\b(?:el|los|las|una|usted|contraseña|contraseñas|artículos|pública|públicos|guías|sesión|administración|buscar|ingresar|descargar|archivos|lectura|escritura|última|volver|demasiados|intentos|nueva|antigua|debe|puede|necesita|contener|caracteres|introduzca|verificar|obligatorio|ha|con|para|que|no hay|más|añadir|modificar|eliminar|guardar|seleccione|seleccionado|actualmente|cambiar|fecha|hora|hoy|ahora|filtro|ninguno)\\b/i;
      const admin = location.pathname.startsWith('/admin/');
      // Athena's dictionary claims a string first; otherwise a match in Django's catalog is a built-in string.
      const check = (value) => {
        // Row controls name the row's own (user) title after the verb.
        const text = value.trim().replace(/^(?:Go to|View|Edit|Delete|Download): .*/s, '');
        if (!text) return;
        const isDjango = admin && django.some((pattern) => pattern.test(text));
        if (spanish.has(text) || !isDjango && languagePattern.test(text)) found.add(text);
        else if (isDjango) builtIn.add(text);
      };
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) {
        const node = walker.currentNode;
        if (AthenaI18n.eligible(node.parentElement) && !node.parentElement.closest('time,.timeline-month>h2,.post-meta,code,.search-result__meta small,.account-main h1,.markdown-section>h1')) check(node.nodeValue);
      }
      for (const element of document.querySelectorAll('[placeholder],[aria-label],[title],input[type=submit]')) {
        if (AthenaI18n.eligible(element)) for (const attr of ['placeholder','aria-label','title', ...(element.matches('input[type=submit]') ? ['value'] : [])]) check(element.getAttribute(attr) || '');
      }
      return [[...found], [...builtIn]];
    })()`);
    console.log(`English interface audit ${name}: ${result.length ? JSON.stringify(result) : '[]'}`);
    if (builtIn.length) console.log(`  Django built-in strings (expected Spanish) ${name}: ${JSON.stringify(builtIn)}`);
    for (const text of builtIn) djangoStrings.set(text, (djangoStrings.get(text) || 0) + 1);
    issues.push(...result.map((text) => name + ': ' + text));
  }
  // Text contrast of every visible text element on its real, composited background (WCAG 2 ratio, computed colours).
  const contrast = [];
  async function measureContrast(name, theme) {
    const rows = await evaluate(`(() => {
      const canvas = document.createElement('canvas'); canvas.width = canvas.height = 1;
      const context = canvas.getContext('2d', { willReadFrequently: true });
      const rgba = (color) => { context.clearRect(0, 0, 1, 1); context.fillStyle = '#000'; context.fillStyle = color; context.fillRect(0, 0, 1, 1); const [r, g, b, a] = context.getImageData(0, 0, 1, 1).data; return [r, g, b, a / 255]; };
      const over = (top, bottom) => top.slice(0, 3).map((value, index) => value * top[3] + bottom[index] * (1 - top[3])).concat(1);
      const luminance = (color) => { const [r, g, b] = color.slice(0, 3).map((value) => { value /= 255; return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
      const ratio = (a, b) => { const [x, y] = [luminance(a), luminance(b)].sort((m, n) => n - m); return (x + 0.05) / (y + 0.05); };
      function background(element) {
        const layers = [];
        for (let node = element; node; node = node.parentElement) {
          const style = getComputedStyle(node);
          if (/url\\(/.test(style.backgroundImage)) return null;
          const color = rgba(style.backgroundColor);
          if (color[3] > 0) layers.push(color);
          if (color[3] >= 1) break;
        }
        return layers.reverse().reduce((base, layer) => over(layer, base), rgba(getComputedStyle(document.documentElement).backgroundColor));
      }
      const tokens = Object.fromEntries(['--text', '--text-muted', '--text-subtle', '--accent-text', '--on-accent', '--crit-text'].map((name) => [rgba(getComputedStyle(document.documentElement).getPropertyValue(name)).join(), name]));
      function role(element, style) {
        if (element.closest('button,.button,input[type=submit],input[type=button],summary.button,[role=tab]')) return 'button text';
        if (element.closest('a')) return 'links';
        if (style.textTransform === 'uppercase' && /Consolas|monospace/.test(style.fontFamily)) return 'labels';
        return { '--text': 'main text', '--text-muted': 'muted text', '--text-subtle': 'subtle text', '--accent-text': 'gold text', '--crit-text': 'error text' }[tokens[rgba(style.color).join()]] || 'other text';
      }
      const rows = [];
      const opaque = (element) => { for (let node = element; node; node = node.parentElement) if (parseFloat(getComputedStyle(node).opacity) < 1) return false; return true; };
      for (const element of document.querySelectorAll('body *')) {
        if (!element.checkVisibility({ visibilityProperty: true }) || ![...element.childNodes].some((node) => node.nodeType === 3 && node.nodeValue.trim())) continue;
        const box = element.getBoundingClientRect();
        if (box.width < 2 || box.height < 2 || element.closest('.visually-hidden,[aria-hidden=true],:disabled,[aria-disabled=true]') || !opaque(element)) continue;
        const style = getComputedStyle(element);
        const ground = background(element);
        if (!ground) continue;
        const ink = over(rgba(style.color), ground);
        rows.push({ role: role(element, style), ratio: Math.round(ratio(ink, ground) * 100) / 100, sample: element.textContent.trim().slice(0, 40), color: style.color, ground: 'rgb(' + ground.slice(0, 3).map(Math.round).join(' ') + ')' });
      }
      for (const field of document.querySelectorAll('input[placeholder],textarea[placeholder]')) {
        if (!field.checkVisibility() || field.disabled) continue;
        const ground = background(field);
        if (ground) rows.push({ role: 'placeholders', ratio: Math.round(ratio(over(rgba(getComputedStyle(field, '::placeholder').color), ground), ground) * 100) / 100, sample: field.placeholder, color: getComputedStyle(field, '::placeholder').color, ground: 'rgb(' + ground.slice(0, 3).map(Math.round).join(' ') + ')' });
      }
      return rows;
    })()`);
    for (const row of rows) contrast.push({ page: name, theme, ...row });
  }
  async function checkLayout(name, theme, lang, width) {
    const state = await evaluate(`(() => {
      const html = document.documentElement;
      const toggles = [...document.querySelectorAll('[data-suite-toggle]')];
      const boxes = toggles.map(x => x.getBoundingClientRect());
      return { width:html.clientWidth, scroll:html.scrollWidth, theme:html.dataset.theme, lang:html.lang, visible:getComputedStyle(document.body).visibility, smallDisplay:[...document.querySelectorAll('body *')].filter(x=>x.checkVisibility() && !x.matches('html[data-rail=compact] .rail-brand span') && [...x.childNodes].some(n=>n.nodeType===3&&n.nodeValue.trim()) && /Cormorant/.test(getComputedStyle(x).fontFamily.split(',')[0]) && parseFloat(getComputedStyle(x).fontSize)<22).map(x=>x.tagName+'.'+x.className+':'+getComputedStyle(x).fontSize), oldFonts:[...document.fonts].filter(f=>/Archivo|Courier|Cascadia|Sigurd/.test(f.family)).map(f=>f.family), clipped:[...document.querySelectorAll('body *')].filter(x=>{ if (!x.checkVisibility({visibilityProperty:true}) || ![...x.childNodes].some(n=>n.nodeType===3&&n.nodeValue.trim())) return false; for (let p=x.parentElement;p&&p!==document.body;p=p.parentElement){ const o=getComputedStyle(p); if (/auto|scroll|hidden|clip/.test(o.overflowX) || o.position==='fixed') return false; } const r=x.getBoundingClientRect(); return r.width>0 && (r.left < -1 || r.right > html.clientWidth + 1); }).map(x=>x.tagName+'.'+x.className+': '+x.textContent.trim().slice(0,30)), lastToggle:toggles.at(-1)?.getBoundingClientRect().right, toggles:boxes.map(x=>({x:x.x,y:x.y,width:x.width,height:x.height})), count:toggles.length, colors:getComputedStyle(html).getPropertyValue('--bg').trim() };
    })()`);
    assert.equal(state.theme, theme, name);
    assert.equal(state.lang, lang, name);
    assert.equal(state.visible, 'visible', name);
    assert(state.scroll <= state.width + 1, `${name}: horizontal scroll ${JSON.stringify(state)}`);
    assert.equal(state.count, 2, name);
    assert.deepEqual(state.smallDisplay, [], `${name}: Cormorant below 22px`);
    assert.deepEqual(state.oldFonts, [], `${name}: old font faces`);
    assert.deepEqual(state.clipped, [], `${name}: text clipped at the viewport edge`);
    assert(state.lastToggle >= width - 48, `${name}: toggles must end at the far right`);
    assert(state.toggles.every((box) => box.width > 0 && box.x >= 0 && box.x + box.width <= width && box.y < 52), `${name}: toggles clipped`);
    if (shots) {
      mkdirSync(shots, { recursive: true });
      const image = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
      writeFileSync(join(shots, `${name}-${theme}-${lang}-${width}.png`), Buffer.from(image.data, 'base64'));
    }
  }
  // Public screens, then the same reader with an isolated test account.
  for (const [name, path] of routes) {
    for (const width of [1440, 390]) for (const theme of ['dark', 'light']) for (const lang of ['es', 'en']) {
      await navigate(path, theme, lang, width);
      await checkLayout(name, theme, lang, width);
      if (lang === 'en' && width === 1440 && theme === 'dark') await audit(name);
      if (lang === 'es' && width === 1440) await measureContrast(name, theme);
    }
  }
  if (session) {
    await send('Network.setCookie', { name: 'sessionid', value: session, url: origin, httpOnly: true, sameSite: 'Lax' });
    for (const [name, path] of [...routes.filter(([name]) => !name.endsWith('signin')), ['downloads', '/#/downloads'], ['account', '/#/account'], ['password', '/accounts/password_change/']]) {
      for (const width of [1440, 390]) for (const [theme, lang] of [['dark', 'en'], ['light', 'es']]) {
        await navigate(path, theme, lang, width);
        await checkLayout(name + '-account', theme, lang, width);
        if (lang === 'en' && width === 1440) await audit(name + '-account');
        if (width === 1440) await measureContrast(name + '-account', theme);
      }
    }
    // Admin pages: every combination of width, theme and language.
    await navigate('/admin/athena/article/', 'dark', 'es');
    const articlePath = await evaluate(`new URL(document.querySelector('#result_list a[href*="/change/"]').href).pathname`);
    const adminRoutes = [['admin-index', '/admin/'], ['admin-articles', '/admin/athena/article/'], ['admin-article-form', articlePath],
      ['admin-users', '/admin/auth/user/'], ['admin-api-keys', '/admin/athena/apikey/'], ['admin-password', '/admin/password_change/']];
    for (const [name, path] of adminRoutes) {
      for (const width of [1440, 390]) for (const theme of ['dark', 'light']) for (const lang of ['es', 'en']) {
        await navigate(path, theme, lang, width);
        await checkLayout(name, theme, lang, width);
        if (lang === 'en' && width === 1440 && theme === 'dark') await audit(name);
        if (lang === 'es' && width === 1440) await measureContrast(name, theme);
      }
    }
    // Admin toggles work in place: theme and language flip, and Athena's own strings follow the language.
    await navigate('/admin/auth/user/', 'dark', 'es');
    await evaluate(`document.querySelector('[data-suite-toggle=theme]').click(); document.querySelector('[data-suite-toggle=lang]').click()`);
    await delay(100);
    assert.deepEqual(await evaluate(`[document.documentElement.dataset.theme, document.documentElement.lang, document.querySelector('#directory-title').textContent, getComputedStyle(document.body).backgroundColor === getComputedStyle(document.documentElement).getPropertyValue('--bg').trim() || getComputedStyle(document.body).backgroundColor]`).then((value) => value.slice(0, 3)), ['light', 'en', 'Users']);
    await evaluate(`document.activeElement.blur()`);
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
    await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
    assert.deepEqual(await evaluate(`(() => { const style = getComputedStyle(document.activeElement); return [document.activeElement.matches(':focus-visible'), style.outlineWidth, style.outlineStyle]; })()`), [true, '2px', 'solid'], 'admin focus outline');
  }
  await navigate('/#/guides', 'light', 'en');
  // Toggles must persist overrides, clear browser-equivalent choices, and translate repeat renders.
  await evaluate(`localStorage.removeItem('suite.athena.theme');document.querySelector('[data-suite-toggle=theme]').click()`);
  assert.equal(await evaluate(`localStorage.getItem('suite.athena.theme')`), 'dark');
  await send('Page.reload'); await ready('/#/guides');
  // The init script selects light on navigation; remove it before checking persistent reload behavior.
  await send('Page.removeScriptToEvaluateOnNewDocument', { identifier: init }); init = null;
  await evaluate(`document.querySelector('[data-suite-toggle=theme]').click()`);
  await send('Page.reload'); await ready('/#/guides');
  assert.equal(await evaluate('document.documentElement.dataset.theme'), 'dark');
  await evaluate(`document.querySelector('[data-suite-toggle=theme]').click()`);
  assert.equal(await evaluate(`localStorage.getItem('suite.athena.theme')`), null);
  const browserLang = await evaluate('SuiteBoot.resolveLang(null,navigator.languages)');
  await evaluate(`document.querySelector('[data-suite-toggle=lang]').click()`);
  const nextLang = await evaluate('document.documentElement.lang');
  assert.equal(await evaluate(`localStorage.getItem('suite.athena.lang')`), nextLang === browserLang ? null : nextLang);
  await send('Page.reload'); await ready('/#/guides');
  assert.equal(await evaluate('document.documentElement.lang'), nextLang);
  await evaluate(`document.querySelector('[data-suite-toggle=lang]').click()`);
  await evaluate(`document.activeElement.blur()`);
  await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
  const focus = await evaluate(`(() => { const style = getComputedStyle(document.activeElement); return [document.activeElement.matches(':focus-visible'), style.outlineWidth, style.outlineOffset]; })()`);
  assert.deepEqual(focus, [true, '2px', '2px']);
  await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
  assert.equal(await evaluate(`getComputedStyle(document.querySelector('[data-suite-toggle=lang]')).transitionDuration`), '0s');
  if (djangoStrings.size) console.log(`Django built-in strings left in Spanish (not failures): ${JSON.stringify([...djangoStrings.keys()])}`);
  const summary = {};
  for (const row of contrast) {
    const key = row.theme + ' · ' + row.role;
    summary[key] = summary[key] || { pairs: 0, min: Infinity, sample: '' };
    summary[key].pairs += 1;
    if (row.ratio < summary[key].min) Object.assign(summary[key], { min: row.ratio, sample: `${row.page}: "${row.sample}" ${row.color} on ${row.ground}` });
  }
  console.log('Contrast (minimum ratio per theme and role):');
  for (const [key, value] of Object.entries(summary).sort()) console.log(`  ${key}: ${value.pairs} pairs, min ${value.min}:1 (${value.sample})`);
  const low = contrast.filter((row) => row.ratio < 4.5);
  for (const row of low) console.log(`  under 4.5:1 ${row.page} ${row.theme} ${row.role} ${row.ratio}:1 "${row.sample}" ${row.color} on ${row.ground}`);
  assert.deepEqual(errors, [], 'No browser runtime errors');
  assert.deepEqual(issues, [], 'No untranslated Spanish interface strings');
  assert.equal(low.length, 0, 'Every text pair must reach 4.5:1');
  console.log('Headless Chrome layout matrix, English interface audit, storage, reload, focus and reduced-motion checks passed.');
} finally {
  socket?.close();
  chrome.kill('SIGTERM');
  await new Promise((resolve) => chrome.once('exit', resolve));
  // Chromium helpers can still write to the profile just after the browser exits.
  rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
}
