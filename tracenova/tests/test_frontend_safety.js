// Offline frontend regressions for safe rendering and UI interactions.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const script = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'static', 'script.js'), 'utf8');
const elements = {};
const document = {
  getElementById(id) {
    if (!elements[id]) {
      elements[id] = {
        value: 'email',
        classList: { remove() {}, add() {} },
        listeners: {},
        addEventListener(type, listener) { this.listeners[type] = listener; },
        innerHTML: '',
        textContent: '',
      };
    }
    return elements[id];
  },
};
const context = vm.createContext({
  document,
  URL,
  fetch: () => { throw new Error('Network must not be used in a renderer test'); },
  alert: () => {},
});
vm.runInContext(script, context);
const injection = '<svg onload=alert(1)>';
const tests = [
  ['email', { email: injection, domain: injection, summary: injection,
      technical_checks: [{source: 'GitHub', status: 'rate_limited'},
        {source: 'Another provider', status: injection}],
      found_in_sources: [{source: injection, description: injection,
        source_url: 'javascript:alert(1)', profiles: [{username: injection,
        profile_url: 'javascript:alert(1)', avatar: 'javascript:alert(1)'}]}] }],
  ['phone', { phone: injection, summary: injection, info_sources: [
      {source: injection, details: {'test': injection}, description: injection}],
      manual_sources: [{source: injection, source_url: 'javascript:alert(1)'}] }],
  ['username', { username: injection, profiles: [
      {platform: injection, profile_url: 'javascript:alert(1)'}],
      sources: [{platform: injection, status: 'unavailable', error: injection}],
      manual_sources: [{platform: injection, profile_url: 'javascript:alert(1)'}] }],
  ['ip', {ip_address: injection, ip_info: {reverse_dns: injection, geo_city: injection}, message: injection}],
  ['domain', {domain: injection, ip_address: injection, ip_info: {reverse_dns: injection}, message: injection}],
  ['url', {url: injection, hostname: injection, message: injection, resolved_ips: [injection]}],
];
for (const [kind, data] of tests) {
  vm.runInContext('displayResults(input)', Object.assign(context, {
    input: {query_type: kind, status: 'success', ...data},
  }));
  const html = elements.resultContent.innerHTML;
  assert(html.includes('&lt;svg'), kind + ': expected escaped HTML');
  assert(!html.includes(injection), kind + ': raw input leaked into HTML');
  assert(!html.includes('href="javascript:'), kind + ': unsafe link in HTML');
  assert(!html.includes('src="javascript:'), kind + ': unsafe image URL');
  if (kind === 'email') assert(html.includes('rate limited'), 'Email source status must be visible');
}
console.log('Frontend safe-rendering tests passed (' + tests.length + ' modes).');

const modal = elements.helpModal;
let open = false;
let focusRestorations = 0;
Object.assign(modal, {
  showModal() { open = true; },
  close() { open = false; this.listeners.close(); },
  getBoundingClientRect() { return {left: 10, right: 50, top: 10, bottom: 50}; },
});
elements.helpIcon.focus = () => { focusRestorations += 1; };
elements.helpIcon.listeners.click();
assert.equal(open, true);
assert.equal(elements.helpTitle.textContent, 'Email Search');
modal.listeners.click({target: modal, clientX: 20, clientY: 20});
assert.equal(open, true, 'clicking inside the dialog keeps it open');
modal.listeners.click({target: modal, clientX: 0, clientY: 0});
assert.equal(open, false);
elements.helpIcon.listeners.click();
elements.closeHelp.listeners.click();
assert.equal(open, false);
assert.equal(focusRestorations, 2);

const animation = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'static', 'interactions.js'), 'utf8');
const frames = new Map();
const motion = {matches: true, addEventListener(_type, listener) { this.change = listener; }};
const gridDocument = {
  readyState: 'loading',
  hidden: false,
  listeners: {},
  getElementById: () => ({getContext: () => ({})}),
  addEventListener(type, listener) { this.listeners[type] = listener; },
};
let frameId = 0;
const gridContext = vm.createContext({
  document: gridDocument,
  window: {innerWidth: 320, innerHeight: 640, matchMedia: () => motion, addEventListener() {}},
  requestAnimationFrame(callback) { frames.set(++frameId, callback); return frameId; },
  cancelAnimationFrame(id) { frames.delete(id); },
});
vm.runInContext(animation, gridContext);
gridDocument.listeners.DOMContentLoaded();
assert.equal(frames.size, 0, 'reduced-motion preference suppresses the canvas loop');
motion.matches = false;
motion.change();
gridDocument.listeners.visibilitychange();
assert.equal(frames.size, 1, 'resuming does not schedule duplicate frames');
gridDocument.hidden = true;
gridDocument.listeners.visibilitychange();
assert.equal(frames.size, 0, 'hiding the tab cancels the scheduled frame');
gridDocument.hidden = false;
gridDocument.listeners.visibilitychange();
assert.equal(frames.size, 1, 'showing the tab resumes the animation');
motion.matches = true;
motion.change();
assert.equal(frames.size, 0, 'enabling reduced motion cancels the resumed frame');
console.log('Help dialog and canvas lifecycle tests passed.');
