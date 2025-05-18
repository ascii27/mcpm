// mcpm-registry/public/package-details.js
document.addEventListener('DOMContentLoaded', () => {
    // --- Package Details Elements ---
    const loadingMsg = document.getElementById('loading-message');
    const errorMsg = document.getElementById('error-message');
    const packageDetails = document.getElementById('package-details');
    
    // Package header elements
    const packageNameEl = document.getElementById('package-name');
    const packageVersionEl = document.getElementById('package-version');
    const packageDownloadsEl = document.getElementById('package-downloads');
    
    // Package metadata elements
    const packageAuthorEl = document.getElementById('package-author');
    const packageUpdatedEl = document.getElementById('package-updated');
    const packageDescriptionEl = document.getElementById('package-description');
    
    // Action buttons
    const downloadBtn = document.getElementById('download-btn');
    const installCmdBtn = document.getElementById('install-cmd-btn');
    const installCommand = document.getElementById('install-command');
    const packageNameCmd = document.getElementById('package-name-cmd');
    const copyCmdBtn = document.getElementById('copy-cmd-btn');
    
    // Version history and dependencies
    const versionHistoryEl = document.getElementById('version-history');
    const dependenciesSection = document.getElementById('dependencies-section');
    const dependenciesList = document.getElementById('dependencies-list');
    
    const API_PACKAGE_BASE_URL = '/api/packages';
    
    // Get package name from URL query parameter
    const urlParams = new URLSearchParams(window.location.search);
    const packageName = urlParams.get('name');
    
    if (!packageName) {
        showError('No package name specified');
        return;
    }
    
    // Fetch package details
    fetchPackageDetails(packageName);
    
    // --- Event Listeners ---
    if (installCmdBtn) {
        installCmdBtn.addEventListener('click', () => {
            installCommand.style.display = installCommand.style.display === 'none' ? 'block' : 'none';
        });
    }
    
    if (copyCmdBtn) {
        copyCmdBtn.addEventListener('click', copyInstallCommand);
    }
    
    if (downloadBtn) {
        downloadBtn.addEventListener('click', () => {
            const version = packageVersionEl.textContent.replace('v', '');
            downloadPackage(packageName, version);
        });
    }
    
    // --- Functions ---
    async function fetchPackageDetails(packageName) {
        loadingMsg.style.display = 'block';
        errorMsg.style.display = 'none';
        packageDetails.style.display = 'none';
        
        try {
            const response = await fetch(`${API_PACKAGE_BASE_URL}/${packageName}`);
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(`Failed to fetch package details: ${response.status} ${response.statusText} - ${errorData.details || errorData.error}`);
            }
            
            const packageData = await response.json();
            displayPackageDetails(packageData);
            
            // Also fetch version history if available
            fetchVersionHistory(packageName);
            
        } catch (error) {
            console.error('Error fetching package details:', error);
            showError(error.message);
        }
    }
    
    async function fetchVersionHistory(packageName) {
        try {
            const response = await fetch(`${API_PACKAGE_BASE_URL}/${packageName}/versions`);
            
            if (!response.ok) {
                console.warn('Version history not available');
                return;
            }
            
            const versions = await response.json();
            displayVersionHistory(versions);
            
        } catch (error) {
            console.warn('Error fetching version history:', error);
            // Don't show error for version history, just hide the section
            document.querySelector('.version-table').style.display = 'none';
        }
    }
    
    function displayPackageDetails(packageData) {
        // Hide loading message and show package details
        loadingMsg.style.display = 'none';
        packageDetails.style.display = 'block';
        
        // Set package name and version
        packageNameEl.textContent = packageData.name;
        packageVersionEl.textContent = `v${packageData.latest_version || 'N/A'}`;
        
        // Set download count if available
        if (packageData.download_count !== undefined) {
            packageDownloadsEl.textContent = `${packageData.download_count} downloads`;
            packageDownloadsEl.style.display = 'inline-block';
        } else {
            packageDownloadsEl.style.display = 'none';
        }
        
        // Set author if available
        if (packageData.author) {
            packageAuthorEl.textContent = packageData.author;
            document.getElementById('author-info').style.display = 'block';
        } else {
            document.getElementById('author-info').style.display = 'none';
        }
        
        // Set last updated date if available
        if (packageData.updated_at) {
            const date = new Date(packageData.updated_at);
            packageUpdatedEl.textContent = date.toLocaleDateString();
            document.getElementById('updated-info').style.display = 'block';
        } else {
            document.getElementById('updated-info').style.display = 'none';
        }
        
        // Set description
        packageDescriptionEl.textContent = packageData.description || 'No description available';
        
        // Set install command
        packageNameCmd.textContent = packageData.name;
        
        // Set dependencies if available
        if (packageData.dependencies && Object.keys(packageData.dependencies).length > 0) {
            dependenciesSection.style.display = 'block';
            dependenciesList.innerHTML = '';
            
            for (const [dep, version] of Object.entries(packageData.dependencies)) {
                const li = document.createElement('li');
                li.innerHTML = `<a href="package-details.html?name=${dep}">${dep}</a> <span class="badge badge-primary">${version}</span>`;
                dependenciesList.appendChild(li);
            }
        } else {
            dependenciesSection.style.display = 'none';
        }
    }
    
    function displayVersionHistory(versions) {
        if (!versions || versions.length === 0) {
            document.querySelector('.version-table').style.display = 'none';
            return;
        }
        
        versionHistoryEl.innerHTML = '';
        
        versions.forEach(version => {
            const row = document.createElement('tr');
            
            // Version number
            const versionCell = document.createElement('td');
            versionCell.textContent = version.version;
            
            // Release date
            const dateCell = document.createElement('td');
            if (version.released_at) {
                const date = new Date(version.released_at);
                dateCell.textContent = date.toLocaleDateString();
            } else {
                dateCell.textContent = 'Unknown';
            }
            
            // Download link
            const downloadCell = document.createElement('td');
            const downloadLink = document.createElement('button');
            downloadLink.className = 'btn btn-sm';
            downloadLink.innerHTML = '<i class="fas fa-download"></i>';
            downloadLink.addEventListener('click', () => downloadPackage(packageName, version.version));
            downloadCell.appendChild(downloadLink);
            
            row.appendChild(versionCell);
            row.appendChild(dateCell);
            row.appendChild(downloadCell);
            
            versionHistoryEl.appendChild(row);
        });
    }
    
    function downloadPackage(packageName, version) {
        const downloadUrl = `${API_PACKAGE_BASE_URL}/${packageName}/${version}/download`;
        window.open(downloadUrl, '_blank');
    }
    
    function copyInstallCommand() {
        const command = document.getElementById('install-cmd-text').textContent;
        
        // Create a temporary textarea element to copy from
        const textarea = document.createElement('textarea');
        textarea.value = command;
        document.body.appendChild(textarea);
        textarea.select();
        
        try {
            document.execCommand('copy');
            
            // Show success message
            const originalText = copyCmdBtn.innerHTML;
            copyCmdBtn.innerHTML = '<i class="fas fa-check"></i> Copied!';
            
            // Reset button text after 2 seconds
            setTimeout(() => {
                copyCmdBtn.innerHTML = originalText;
            }, 2000);
            
        } catch (err) {
            console.error('Failed to copy text: ', err);
        } finally {
            document.body.removeChild(textarea);
        }
    }
    
    function showError(message) {
        loadingMsg.style.display = 'none';
        packageDetails.style.display = 'none';
        errorMsg.textContent = `Error: ${message}`;
        errorMsg.style.display = 'block';
    }
});
