// Offline regression tests: API text must never become executable HTML.
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
        addEventListener() {},
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
