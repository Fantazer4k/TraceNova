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
        text: "Enter a domain name (e.g., example.com) to get comprehensive information about the website, including IP address, hosting provider, SSL certificate, technologies used, and security details."
    },
    url: {
        title: "URL Search",
        text: "Enter a full URL (e.g., https://example.com/page) to analyze the website and extract metadata, headers, and page information."
    },
    ip: {
        title: "IP Address Search",
        text: "Enter an IP address (e.g., 192.168.1.1) to discover hosting information, geolocation, ASN details, and associated domains."
    },
    username: {
        title: "Username Search",
        text: "Enter a username to find public profiles across social media platforms, GitHub, and other services where this username appears."
    },
    email: {
        title: "Email Search",
        text: "Enter an email address to find where it appears publicly - data breaches, GitHub profiles, social media, and other internet sources."
    },
    phone: {
        title: "Phone Number Search",
        text: "Enter a phone number to get comprehensive information including country, carrier, type (mobile/landline), location, and data breach history."
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
        helpModal.classList.remove('hidden');
    }
});

closeHelp.addEventListener('click', () => {
    helpModal.classList.add('hidden');
});

helpModal.addEventListener('click', (e) => {
    if (e.target === helpModal) {
        helpModal.classList.add('hidden');
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
        phone: '+1-555-0123'
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
        const response = await fetch(`/api/analyze?query=${query}&query_type=${type}`);
        const data = await response.json();
        displayResults(data);
    } catch (error) {
        resultContent.innerHTML = `<p>Error: ${error.message}</p>`;
    } finally {
        analyzeBtn.disabled = false;
        analyzeBtn.textContent = 'Analyze';
    }
}

function displayResults(data) {
    resultsSection.classList.remove('hidden');

    // Handle errors
    if (data.status === "error") {
        resultContent.innerHTML = `
            <div class="result-error">
                <h3>❌ Analysis Failed</h3>
                <p><strong>Query:</strong> ${data.domain || data.username || data.query}</p>
                <p><strong>Error:</strong> ${data.message}</p>
            </div>
        `;
        return;
    }

    // Handle IP Address (Domain) search
    if (data.ip_address) {
        resultContent.innerHTML = `
            <div class="result-card">
                <h3>✅ ${data.domain}</h3>

                <div class="result-item">
                    <strong>IP Address:</strong>
                    <span class="ip-address">${data.ip_address}</span>
                </div>

                ${data.ip_info && data.ip_info.reverse_dns !== "N/A" ? `
                    <div class="result-item">
                        <strong>Reverse DNS:</strong>
                        <span>${data.ip_info.reverse_dns}</span>
                    </div>
                ` : ''}

                <p class="result-message">${data.message}</p>
            </div>
        `;
        return;
    }

    // Handle Username search
    if (data.profiles !== undefined) {
        if (data.profiles_found === 0) {
            resultContent.innerHTML = `
                <div class="result-card">
                    <h3>ℹ️ No profiles found</h3>
                    <p>No public profiles found with username <strong>"${data.username}"</strong></p>
                </div>
            `;
            return;
        }

        let profilesHTML = data.profiles.map(profile => `
            <div class="profile-item">
                <div class="profile-header">
                    <span class="platform-badge">${profile.platform}</span>
                    <span class="status-badge ${profile.found ? 'found' : 'not-found'}">
                        ${profile.found ? '✓ Found' : '✗ Not Found'}
                    </span>
                </div>
                ${profile.profile_url ? `
                    <a href="${profile.profile_url}" target="_blank" class="profile-link">
                        ${profile.profile_url}
                    </a>
                ` : ''}
                ${profile.error ? `<p class="error-text">${profile.error}</p>` : ''}
            </div>
        `).join('');

        resultContent.innerHTML = `
            <div class="result-card">
                <h3>🔍 "${data.username}" - Found ${data.profiles_found} profile(s)</h3>
                <div class="profiles-list">
                    ${profilesHTML}
                </div>
                <p class="result-message">${data.message}</p>
            </div>
        `;
        return;
    }

    // Handle Phone search
    if (data.phone) {
        console.log('Phone search result:', data);

        if (data.status === "error") {
            resultContent.innerHTML = `
                <div class="result-error">
                    <h3>❌ Invalid Phone</h3>
                    <p><strong>Phone:</strong> ${data.phone}</p>
                    <p><strong>Error:</strong> ${data.message}</p>
                </div>
            `;
            return;
        }

        if (data.status === "no_results" || !data.found_in_sources || data.found_in_sources.length === 0) {
            resultContent.innerHTML = `
                <div class="result-card">
                    <h3>✓ Phone Search Complete</h3>
                    <div class="email-summary">
                        <strong>Phone:</strong> ${data.phone}<br>
                        <strong>Summary:</strong> ${data.summary || 'No results found'}
                    </div>
                </div>
            `;
            return;
        }

        if (data.found_in_sources && data.found_in_sources.length > 0) {
            let sourcesHTML = '';

            for (const source of data.found_in_sources) {
                let badgeClass = 'source-badge';
                if (source.type === 'security_alert') badgeClass += ' badge-alert';
                if (source.type === 'verification') badgeClass += ' badge-verify';
                if (source.type === 'real_search') badgeClass += ' badge-search';

                sourcesHTML += `
                    <div class="email-source-item" data-type="${source.type || 'default'}">
                        <div class="source-header">
                            <span class="${badgeClass}">${source.icon || '•'} ${source.source}</span>
                            ${source.warning ? `<span class="warning-badge">${source.warning}</span>` : ''}
                        </div>
                        <div class="source-content">
                            <p class="source-description">${source.description}</p>
                            ${source.note ? `<p class="source-note">${source.note}</p>` : ''}

                            ${source.details ? `
                                <div class="details-grid">
                                    ${Object.entries(source.details).map(([key, value]) => `
                                        <div class="detail-item">
                                            <span class="detail-key">${key}:</span>
                                            <span class="detail-value">${value}</span>
                                        </div>
                                    `).join('')}
                                </div>
                            ` : ''}

                            ${source.breaches && source.breaches.length > 0 ? `
                                <div class="breach-list">
                                    ${source.breaches.map(b => `
                                        <span class="breach-tag">${b}</span>
                                    `).join('')}
                                </div>
                            ` : ''}

                            ${source.source_url ? `
                                <a href="${source.source_url}" target="_blank" class="source-link">
                                    Learn more →
                                </a>
                            ` : ''}
                        </div>
                    </div>
                `;
            }

            resultContent.innerHTML = `
                <div class="result-card">
                    <h3>☎️ ${data.phone}</h3>
                    <p class="email-summary">${data.summary}</p>
                    <div class="email-sources-list">
                        ${sourcesHTML}
                    </div>
                </div>
            `;
            return;
        }
    }

    // Handle Email search
    if (data.email) {
        console.log('Email search result:', data);

        // Handle error status
        if (data.status === "error") {
            resultContent.innerHTML = `
                <div class="result-error">
                    <h3>❌ Invalid Email</h3>
                    <p><strong>Email:</strong> ${data.email}</p>
                    <p><strong>Error:</strong> ${data.message}</p>
                </div>
            `;
            return;
        }

        // Handle no results
        if (data.status === "no_results" || !data.found_in_sources || data.found_in_sources.length === 0) {
            resultContent.innerHTML = `
                <div class="result-card">
                    <h3>✓ Email Search Complete</h3>
                    <div class="email-summary">
                        <strong>Email:</strong> ${data.email}<br>
                        <strong>Summary:</strong> ${data.summary || 'No public sources found'}
                    </div>
                </div>
            `;
            return;
        }

        // Handle found sources
        if (data.found_in_sources && data.found_in_sources.length > 0) {
            let sourcesHTML = '';

            for (const source of data.found_in_sources) {
                let badgeClass = 'source-badge';
                if (source.type === 'security_alert') badgeClass += ' badge-alert';
                if (source.type === 'verification') badgeClass += ' badge-verify';
                if (source.type === 'real_search') badgeClass += ' badge-search';

                sourcesHTML += `
                    <div class="email-source-item" data-type="${source.type || 'default'}">
                        <div class="source-header">
                            <span class="${badgeClass}">${source.icon || '•'} ${source.source}</span>
                            ${source.warning ? `<span class="warning-badge">${source.warning}</span>` : ''}
                        </div>
                        <div class="source-content">
                            <p class="source-description">${source.description}</p>
                            ${source.note ? `<p class="source-note">${source.note}</p>` : ''}

                            ${source.profiles && source.profiles.length > 0 ? `
                                <div class="github-profiles">
                                    ${source.profiles.map(p => `
                                        <a href="${p.profile_url}" target="_blank" class="github-profile">
                                            <img src="${p.avatar}" alt="${p.username}" class="profile-avatar">
                                            <span>${p.username}</span>
                                        </a>
                                    `).join('')}
                                </div>
                            ` : ''}

                            ${source.breaches && source.breaches.length > 0 ? `
                                <div class="breach-list">
                                    ${source.breaches.map(b => `
                                        <span class="breach-tag">${b}</span>
                                    `).join('')}
                                </div>
                            ` : ''}

                            ${source.source_url ? `
                                <a href="${source.source_url}" target="_blank" class="source-link">
                                    ${source.type === 'alternative_tool' ? 'Visit' : 'Learn more'} →
                                </a>
                            ` : ''}
                        </div>
                    </div>
                `;
            }

            resultContent.innerHTML = `
                <div class="result-card">
                    <h3>📧 ${data.email}</h3>
                    <p class="email-summary">${data.summary}</p>
                    <div class="email-sources-list">
                        ${sourcesHTML}
                    </div>
                </div>
            `;
            return;
        }
    }

    // Default fallback
    resultContent.innerHTML = `
        <div class="result-card">
            <h3>${data.query}</h3>
            <p><strong>Status:</strong> ${data.status}</p>
            <p>${data.message}</p>
        </div>
    `;
}
