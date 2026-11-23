function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    })[char]);
}

function safeExternalUrl(value) {
    try {
        const url = new URL(String(value || ''));
        if (url.protocol !== 'https:' && url.protocol !== 'http:') return '';
        return escapeHtml(url.href);
    } catch {
        return '';
    }
}

const analyzeBtn = document.getElementById('analyzeBtn');
const queryInput = document.getElementById('queryInput');
const queryLabel = document.getElementById('queryLabel');
const queryType = document.getElementById('queryType');
const resultsSection = document.getElementById('results');
const resultContent = document.getElementById('resultContent');
const helpIcon = document.getElementById('helpIcon');
const helpModal = document.getElementById('helpModal');
const closeHelp = document.getElementById('closeHelp');
const searchStatus = document.getElementById('searchStatus');
const exampleTitle = document.getElementById('exampleTitle');
const exampleDescription = document.getElementById('exampleDescription');
const exampleQuery = document.getElementById('exampleQuery');
let activeRequest = null;

const lookupExamples = {
    domain: ['Domain name', 'example.com', 'Try a domain lookup',
        'Look up DNS records for example.com, a domain reserved for documentation.'],
    url: ['URL', 'https://example.com', 'Try a URL lookup',
        'Check DNS records and HTTPS certificate details for https://example.com.'],
    ip: ['IP address', '192.0.2.1', 'Try an IP lookup',
        'Check 192.0.2.1, an address reserved for documentation.'],
    username: ['Username', 'octocat', 'Try a username lookup',
        'Look for exact public matches for octocat, GitHub’s example account.'],
    email: ['Email address', 'email@example.com', 'Try an email lookup',
        'Check email@example.com, an illustrative address on a documentation domain.'],
    phone: ['Phone number', '+123456789', 'Try a phone lookup',
        'See how TraceNova reports a number that does not fit its numbering plan.']
};

// Help content for each search type
const helpContent = {
    domain: {
        title: "Domain Search",
        text: "Enter a domain name to look up IPv4 and IPv6 records and available reverse DNS data."
    },
    url: {
        title: "URL Search",
        text: "Enter a full URL (e.g., https://example.com/page) to inspect its hostname, public DNS addresses, and HTTPS/TLS certificate. Page content is not fetched."
    },
    ip: {
        title: "IP Address Search",
        text: "Enter an IPv4 or IPv6 address to check public/private status, reverse DNS, network registration, and approximate ASN/location when providers are available. This does not identify a person or all domains on an IP."
    },
    username: {
        title: "Username Search",
        text: "Enter an exact username. TraceNova shows links for confirmed public matches and a short result for each platform."
    },
    email: {
        title: "Email Search",
        text: "Check the configured public email-related sources and technical signals. A missing match does not prove an email address is unused; not all social sites support email search."
    },
    phone: {
        title: "Phone Number Search",
        text: "Enter a phone number in international format to check numbering-plan validity, inferred region and original carrier, plus manual public-web links. No phone breach lookup is performed."
    }
};

document.getElementById('searchForm').addEventListener('submit', (event) => {
    event.preventDefault();
    return analyze();
});

// Help icon functionality
helpIcon.addEventListener('click', () => {
    const type = queryType.value;
    const help = helpContent[type];
    if (help) {
        document.getElementById('helpTitle').textContent = help.title;
        document.getElementById('helpText').textContent = help.text;
        helpModal.showModal();
    }
});

closeHelp.addEventListener('click', () => {
    helpModal.close();
});

helpModal.addEventListener('close', () => helpIcon.focus());

helpModal.addEventListener('click', (event) => {
    if (event.target !== helpModal) return;
    const bounds = helpModal.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right ||
        event.clientY < bounds.top || event.clientY > bounds.bottom) {
        helpModal.close();
    }
});

queryType.addEventListener('change', () => {
    activeRequest?.abort();
    activeRequest = null;
    setLoading(false);
    searchStatus.textContent = '';
    queryInput.removeAttribute('aria-invalid');
    resultsSection.classList.add('hidden');
    resultContent.textContent = '';
    const [label, placeholder, title, description] = lookupExamples[queryType.value] || lookupExamples.domain;
    queryLabel.textContent = label;
    queryInput.placeholder = placeholder;
    exampleTitle.textContent = title;
    exampleDescription.textContent = description;
    exampleQuery.textContent = 'Use ' + placeholder;
});

queryInput.addEventListener('input', () => {
    if (queryInput.hasAttribute('aria-invalid')) {
        queryInput.removeAttribute('aria-invalid');
        searchStatus.textContent = '';
    }
});

exampleQuery.addEventListener('click', () => {
    const [, value] = lookupExamples[queryType.value] || lookupExamples.domain;
    queryInput.value = value;
    if (queryInput.hasAttribute('aria-invalid')) {
        queryInput.removeAttribute('aria-invalid');
        searchStatus.textContent = '';
    }
    queryInput.focus();
});

function setLoading(loading) {
    analyzeBtn.disabled = loading;
    analyzeBtn.textContent = loading ? 'Analyzing…' : 'Analyze';
    resultsSection.setAttribute('aria-busy', String(loading));
}

async function analyze() {
    if (activeRequest) return;
    const query = queryInput.value.trim();
    const type = queryType.value;

    if (!query) {
        searchStatus.textContent = 'Enter a query to begin.';
        queryInput.setAttribute('aria-invalid', 'true');
        queryInput.focus();
        return;
    }

    queryInput.removeAttribute('aria-invalid');
    const request = new AbortController();
    activeRequest = request;
    setLoading(true);
    resultsSection.classList.remove('hidden');
    searchStatus.textContent = 'Checking sources…';
    resultContent.innerHTML = `
        <div class="result-card result-loading">
            <h3>Analysis in progress</h3>
            <div class="result-skeleton" aria-hidden="true">
                <span></span><span></span><span></span>
            </div>
        </div>`;

    try {
        const response = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, query_type: type }),
            signal: request.signal
        });
        const data = await response.json().catch(() => null);
        if (activeRequest !== request) return;

        if (!response.ok) {
            throw new Error(typeof data?.detail === 'string' ? data.detail : `Request failed (HTTP ${response.status})`);
        }

        displayResults(data);
        searchStatus.textContent = !data || typeof data !== 'object' || data.status === 'error'
            ? 'Analysis failed. See the details below.'
            : 'Analysis complete. Results are below.';
    } catch (error) {
        if (activeRequest !== request) return;
        searchStatus.textContent = 'Analysis failed. See the details below.';
        resultContent.innerHTML = errorCard('Analysis failed', '', error.message);
    } finally {
        if (activeRequest === request) {
            activeRequest = null;
            setLoading(false);
        }
    }
}

// Every value from the API is untrusted. Build HTML only through these helpers.
function valueText(value) {
    if (value === null || value === undefined) return '';
    if (Array.isArray(value)) return value.map(valueText).join(', ');
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
}

function field(label, value) {
    if (value === null || value === undefined || value === '') return '';
    return '<div class="result-item"><strong>' + escapeHtml(label) +
        ':</strong><span>' + escapeHtml(valueText(value)) + '</span></div>';
}

function externalLink(url, label, cssClass) {
    const href = safeExternalUrl(url);
    if (!href) return '';
    const cls = cssClass === 'profile-link' ? 'profile-link' : 'source-link';
    return '<a href="' + href + '" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer" class="' +
        cls + '">' + escapeHtml(label || url) + '</a>';
}

function errorCard(title, value, message) {
    return '<div class="result-error"><h3>' + escapeHtml(title) + '</h3>' +
        (value ? field('Query', value) : '') +
        '<p>' + escapeHtml(message || 'The analysis could not be completed.') + '</p></div>';
}

function detailsMarkup(details) {
    if (!details || typeof details !== 'object' || Array.isArray(details)) return '';
    return '<div class="details-grid">' + Object.entries(details).map(([key, value]) =>
        '<div class="detail-item"><span class="detail-key">' + escapeHtml(key) +
        ':</span><span class="detail-value">' + escapeHtml(valueText(value)) +
        '</span></div>'
    ).join('') + '</div>';
}

function statusBadge(status) {
    if (!status) return '';
    const labels = {
        found: 'Verified match', checked: 'Checked', checked_no_match: 'No match',
        not_found: 'No match', no_mx: 'No MX record', null_mx: 'Null MX',
        nxdomain: 'Domain not found', rate_limited: 'Rate limited',
        not_configured: 'Not configured', candidates_unverified: 'Unverified candidates',
        unavailable: 'Unavailable', timeout: 'Timed out', error: 'Error',
        incomplete: 'Incomplete', verification_failed: 'Verification failed',
    };
    const tone = ['found', 'checked'].includes(status) ? 'confirmed'
        : ['rate_limited', 'unavailable', 'timeout', 'error', 'incomplete', 'verification_failed'].includes(status)
            ? 'attention' : 'neutral';
    const label = Object.hasOwn(labels, status) ? labels[status] : String(status).replaceAll('_', ' ');
    return '<span class="status-badge status-' + tone + '">' + escapeHtml(label) + '</span>';
}

function coverageNotice(sources, emptyMessage) {
    const incomplete = sources.some(source => source && [
        'unavailable', 'timeout', 'error', 'rate_limited', 'incomplete',
    ].includes(source.status));
    if (incomplete) {
        return '<p class="result-notice result-notice-attention"><strong>Partial coverage.</strong> ' +
            'Some sources could not complete their checks. See the source statuses below.</p>';
    }
    return emptyMessage ? '<p class="result-notice">' + escapeHtml(emptyMessage) + '</p>' : '';
}

function sourceCard(source) {
    if (!source || typeof source !== 'object') return '';
    const profiles = Array.isArray(source.profiles) ? source.profiles : [];
    const breaches = Array.isArray(source.breaches) ? source.breaches : [];
    const webResults = Array.isArray(source.results) ? source.results : [];
    const profileHtml = profiles.map(p => {
        const avatar = safeExternalUrl(p.avatar);
        const avatarHtml = avatar ? '<img src="' + avatar + '" alt="" class="profile-avatar" referrerpolicy="no-referrer">' : '';
        return '<div class="github-profile">' + avatarHtml +
            externalLink(p.profile_url, p.username || 'Public profile', 'profile-link') + '</div>';
    }).join('');
    return '<div class="email-source-item"><div class="source-header"><span class="source-badge">' +
        escapeHtml(source.icon || '•') + ' ' + escapeHtml(source.source || source.platform || 'Source') +
        '</span>' + statusBadge(source.status) +
        '</div><div class="source-content">' +
        (source.description ? '<p class="source-description">' + escapeHtml(source.description) + '</p>' : '') +
        (source.note ? '<p class="source-note">' + escapeHtml(source.note) + '</p>' : '') +
        detailsMarkup(source.details) + profileHtml +
        (breaches.length ? '<div class="breach-list">' + breaches.map(b =>
            '<span class="breach-tag">' + escapeHtml(valueText(b)) + '</span>').join('') + '</div>' : '') +
        webResults.map(r => '<article class="public-web-result">' +
            externalLink(r.url, r.title || r.domain || 'Public page') +
            (r.snippet ? '<p>' + escapeHtml(r.snippet) + '</p>' : '') + '</article>').join('') +
        externalLink(source.source_url, 'Open source') + '</div></div>';
}

function section(title, content) {
    return content ? '<section class="result-group"><h4>' + escapeHtml(title) +
        '</h4><div class="email-sources-list">' + content + '</div></section>' : '';
}

function manualLinks(items, urlField) {
    return (Array.isArray(items) ? items : []).map(m =>
        '<div class="profile-item">' +
        externalLink(m[urlField] || m.source_url, m.platform || m.source || 'Manual lookup', 'profile-link') +
        '<span class="source-note"> — Manual check, not a verified match</span></div>'
    ).join('');
}

function displayResults(data) {
    resultsSection.classList.remove('hidden');
    if (!data || typeof data !== 'object') {
        resultContent.innerHTML = errorCard('Invalid response', '', 'The server did not return valid data.');
        return;
    }
    const kind = data.query_type || queryType.value;
    if (data.status === 'error') {
        resultContent.innerHTML = errorCard('Analysis failed',
            data.url || data.domain || data.username || data.email || data.phone ||
            data.ip_address || data.query || '', data.message);
        return;
    }

    if (kind === 'url') {
        const tls = data.tls || {};
        resultContent.innerHTML = '<div class="result-card"><h3>URL analysis</h3>' +
            field('URL', data.url) + field('Hostname', data.hostname) +
            field('Scheme', data.scheme) + field('Port', data.port) +
            field('Path', data.path) + field('Resolved IPs', data.resolved_ips) +
            field('TLS status', data.scheme === 'https' ? (tls.status || 'unknown') : 'Not applicable (HTTP)') +
            field('TLS version', tls.version) + field('Certificate expiry', tls.expires) +
            field('TLS note', tls.message) + field('TLS endpoint', tls.connected_ip) +
            field('TLS endpoints checked', tls.checked_endpoints) +
            field('Summary', data.message) + '</div>';
        return;
    }

    if (kind === 'ip') {
        const ip = data.ip_info || {};
        resultContent.innerHTML = '<div class="result-card"><h3>IP Address Analysis</h3>' +
            field('IP', data.ip_address) + field('Version', data.ip_version) +
            field('Address classification', ip.address_type) +
            field('Reverse DNS', ip.reverse_dns) +
            field('Registered network', ip.network_name) +
            field('Registry country', ip.network_country) +
            field('Registered IP range', ip.network_range) +
            field('ASN', ip.asn) + field('ISP', ip.isp) +
            field('Approximate country', ip.geo_country) +
            field('Approximate region', ip.geo_region) +
            field('Approximate city', ip.geo_city) +
            field('Registry source', ip.registry_source) +
            field('Approximate location source', ip.geolocation_source) +
            field('Registry note', ip.registry_note) +
            field('Geolocation note', ip.geolocation_note) +
            '<p class="source-note">Approximate IP geolocation is not a precise physical location.</p>' +
            field('Summary', data.message) + '</div>';
        return;
    }

    if (kind === 'domain') {
        const ip = data.ip_info || {};
        resultContent.innerHTML = '<div class="result-card"><h3>Domain DNS Analysis</h3>' +
            field('Domain', data.domain) + field('Primary address', data.ip_address) +
            field('IPv4 addresses', data.ip_addresses) +
            field('IPv6 addresses', data.ipv6_addresses) +
            field('Reverse DNS', ip.reverse_dns) +
            field('Summary', data.message) + '</div>';
        return;
    }

    if (kind === 'username') {
        const profiles = Array.isArray(data.profiles) ? data.profiles : [];
        const checked = Array.isArray(data.sources) ? data.sources : [];
        const names = new Map(Object.entries({
            github: 'GitHub', gitlab: 'GitLab', reddit: 'Reddit', keybase: 'Keybase',
            hackernews: 'Hacker News', devto: 'DEV Community', codeberg: 'Codeberg',
            bluesky: 'Bluesky', x: 'X', youtube: 'YouTube', instagram: 'Instagram',
            tiktok: 'TikTok', facebook: 'Facebook', telegram: 'Telegram', vk: 'VK',
            snapchat: 'Snapchat', pinterest: 'Pinterest', tumblr: 'Tumblr',
            stackoverflow: 'Stack Overflow', pastebin: 'Pastebin'
        }));
        const matches = new Map(profiles.map(profile => [profile.platform, profile]));
        const platforms = new Map([...checked, ...profiles].map(source => [source.platform, source]));
        const rows = Array.from(platforms, ([platform, source]) => {
            const name = names.get(platform) || platform;
            const url = matches.get(platform)?.profile_url;
            const link = externalLink(url, url, 'profile-link');
            let message = 'Could not verify a match on ' + name + '.';
            if (source.status === 'not_found') {
                message = 'No user with this username was found on ' + name + '.';
            } else if (source.reason === 'not_configured') {
                message = name + ' lookup is not configured.';
            } else if (source.reason === 'unsupported') {
                message = name + ' lookup is not supported.';
            } else if (source.status === 'rate_limited') {
                message = name + ' temporarily limited requests.';
            } else if (source.status === 'timeout') {
                message = name + ' did not respond in time.';
            }
            return '<li class="profile-item">' +
                (link ? '<span class="platform-badge">' + escapeHtml(name) + '</span> ' + link
                    : escapeHtml(message)) + '</li>';
        }).join('');
        resultContent.innerHTML = '<div class="result-card"><h3>Username: ' +
            escapeHtml(data.username) + '</h3>' +
            '<ul class="profiles-list" aria-label="Results by platform">' + rows + '</ul>' +
            '</div>';
        return;
    }

    if (kind === 'phone') {
        const confirmed = (Array.isArray(data.found_in_sources) ? data.found_in_sources : []).map(sourceCard).join('');
        const info = (Array.isArray(data.info_sources) ? data.info_sources : []).map(sourceCard).join('');
        resultContent.innerHTML = '<div class="result-card"><h3>Phone Search</h3>' +
            field('Number', data.phone) + field('Summary', data.summary) +
            section('Verified public matches', confirmed) +
            section('Technical number information (not public matches)', info) +
            section('Manual searches — unverified', manualLinks(data.manual_sources, 'source_url')) +
            '</div>';
        return;
    }

    if (kind === 'email') {
        const confirmed = (Array.isArray(data.found_in_sources) ? data.found_in_sources : []).map(sourceCard).join('');
        const technical = Array.isArray(data.technical_checks) ? data.technical_checks : [];
        const checks = technical.map(sourceCard).join('');
        resultContent.innerHTML = '<div class="result-card"><h3>Email Search</h3>' +
            field('Email', data.email) + field('Domain', data.domain) +
            field('Summary', data.summary) +
            coverageNotice(technical, confirmed ? '' : 'No confirmed matches were returned.') +
            section('Verified public sources', confirmed) +
            section('Technical checks', checks) +
            section('Manual searches — unverified', manualLinks(data.manual_sources, 'source_url')) +
            '</div>';
        return;
    }

    resultContent.innerHTML = '<div class="result-card"><h3>Analysis result</h3>' +
        field('Query', data.query) + field('Status', data.status) +
        field('Message', data.message) + '</div>';
}
