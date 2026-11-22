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
const queryType = document.getElementById('queryType');
const resultsSection = document.getElementById('results');
const resultContent = document.getElementById('resultContent');
const helpIcon = document.getElementById('helpIcon');
const helpModal = document.getElementById('helpModal');
const closeHelp = document.getElementById('closeHelp');

// Help content for each search type
const helpContent = {
    domain: {
        title: "Domain Search",
        text: "Enter a domain name to resolve its IPv4 address and available reverse DNS data. This is not a full website security audit."
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
        text: "Check matching usernames using public structured APIs (GitHub, GitLab, Reddit, Bluesky and others). Instagram, TikTok, X and Telegram are candidate links for manual checking, not verified accounts."
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

analyzeBtn.addEventListener('click', analyze);
queryInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') analyze();
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
    const type = queryType.value;
    const placeholders = {
        domain: 'example.com',
        url: 'https://example.com',
        ip: '8.8.8.8',
        username: 'username',
        email: 'email@example.com',
        phone: '+353851234567'
    };
    queryInput.placeholder = placeholders[type] || 'Enter search query...';
});

async function analyze() {
    const query = queryInput.value.trim();
    const type = queryType.value;

    if (!query) {
        alert('Please enter a query');
        return;
    }

    analyzeBtn.disabled = true;
    analyzeBtn.textContent = 'Analyzing...';

    try {
        const response = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, query_type: type })
        });
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || `Request failed (HTTP ${response.status})`);
        }

        displayResults(data);
    } catch (error) {
        resultsSection.classList.remove('hidden');
        resultContent.innerHTML = `<div class="result-error"><h3>Analysis failed</h3><p>${escapeHtml(error.message)}</p></div>`;
    } finally {
        analyzeBtn.disabled = false;
        analyzeBtn.textContent = 'Analyze';
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

function sourceCard(source) {
    if (!source || typeof source !== 'object') return '';
    const status = source.status ? String(source.status).replaceAll('_', ' ') : '';
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
        '</span>' + (status ? '<span class="status-badge">' + escapeHtml(status) + '</span>' : '') +
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
    return content ? '<h4>' + escapeHtml(title) + '</h4><div class="email-sources-list">' + content + '</div>' : '';
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
        const found = profiles.map(p => '<div class="profile-item">' +
            '<span class="platform-badge">' + escapeHtml(p.platform) + '</span> ' +
            externalLink(p.profile_url, 'Verified public profile', 'profile-link') + '</div>').join('');
        const checkedHtml = checked.map(p => '<div class="profile-item">' +
            '<span class="platform-badge">' + escapeHtml(p.platform) + '</span> ' +
            '<span class="status-badge">' + escapeHtml(p.status) + '</span>' +
            (p.error ? ' <span class="source-note">' + escapeHtml(p.error) + '</span>' : '') +
            '</div>').join('');
        resultContent.innerHTML = '<div class="result-card"><h3>Username: ' +
            escapeHtml(data.username) + '</h3>' +
            field('Verified profiles', profiles.length) +
            field('Summary', data.message) +
            section('Verified public profiles', found) +
            section('Candidate links — not confirmed (Instagram, TikTok, X, Telegram and others)',
                manualLinks(data.manual_sources, 'profile_url')) +
            (checkedHtml ? '<details><summary>API check status (' + checked.length +
                ')</summary>' + checkedHtml + '</details>' : '') +
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
        const checks = (Array.isArray(data.technical_checks) ? data.technical_checks : []).map(sourceCard).join('');
        resultContent.innerHTML = '<div class="result-card"><h3>Email Search</h3>' +
            field('Email', data.email) + field('Domain', data.domain) +
            field('Summary', data.summary) +
            (confirmed ? section('Verified public sources', confirmed) :
                '<p class="source-note">No confirmed matches; this does not establish absence.</p>') +
            section('Technical checks', checks) +
            section('Manual searches — unverified', manualLinks(data.manual_sources, 'source_url')) +
            '</div>';
        return;
    }

    resultContent.innerHTML = '<div class="result-card"><h3>Analysis result</h3>' +
        field('Query', data.query) + field('Status', data.status) +
        field('Message', data.message) + '</div>';
}
