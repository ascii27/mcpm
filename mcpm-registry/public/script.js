// mcpm-registry/public/script.js
document.addEventListener('DOMContentLoaded', () => {
    // --- Existing Package Elements ---
    const packageListEl = document.getElementById('package-list');
    const listLoadingMsg = document.getElementById('list-loading-message');
    const listErrorMsg = document.getElementById('list-error-message');

    const publishForm = document.getElementById('publish-form');
    const packageFileInput = document.getElementById('package-file');
    const metadataInput = document.getElementById('metadata');
    const publishStatusMsg = document.getElementById('publish-status-message');
    const publishErrorMsg = document.getElementById('publish-error-message');

    // --- New Server Elements ---
    const serverListEl = document.getElementById('server-list');
    const serverListLoadingMsg = document.getElementById('server-list-loading-message');
    const serverListErrorMsg = document.getElementById('server-list-error-message');
    const registerServerForm = document.getElementById('register-server-form');
    const serverNameInput = document.getElementById('server-name');
    const serverGithubUrlInput = document.getElementById('server-github-url');
    const serverLanguageInput = document.getElementById('server-language');
    const serverConfigInput = document.getElementById('server-config-command');
    const registerStatusMsg = document.getElementById('register-status-message');
    const registerErrorMsg = document.getElementById('register-error-message');

    const API_PACKAGE_BASE_URL = '/api/packages'; // Renamed for clarity
    const API_SERVER_BASE_URL = '/api/servers'; // New base URL for servers

    // Get the config command textarea
    const configCommandTextarea = document.getElementById('server-config-command'); // Corrected ID

    // Set the placeholder with newline characters, matching server default
    if (configCommandTextarea) {
         // Match the default structure from server.js, but use placeholder text
         configCommandTextarea.placeholder = '{\n  "mcpServers": {\n    "github": {\n      "command": "npx",\n      "args": [\n        "-y",\n        "@modelcontextprotocol/server-github"\n      ],\n    }\n  }\n}';
    }

    // --- Package Functions (Existing - Renamed base URL variable) ---
    async function fetchAndDisplayPackages() {
        listLoadingMsg.style.display = 'block';
        listErrorMsg.textContent = '';
        packageListEl.innerHTML = ''; // Clear previous list

        try {
            const response = await fetch(`${API_PACKAGE_BASE_URL}/`); // Use renamed variable
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(`Failed to fetch packages: ${response.status} ${response.statusText} - ${errorData.details || errorData.error}`);
            }
            const packages = await response.json();

            if (packages.length === 0) {
                packageListEl.innerHTML = '<li>No packages found in the registry.</li>';
            } else {
                packages.forEach(pkg => {
                    const li = document.createElement('li');
                    // Basic display - could add download links later
                    li.innerHTML = `
                        <strong>${pkg.name}</strong> (v${pkg.latest_version || 'N/A'}) - ${pkg.description || 'No description'}
                        <button class="delete-package-btn" data-name="${pkg.name}">Delete</button>
                    `; // Added Delete Button
                    packageListEl.appendChild(li);
                });
            }
        } catch (error) {
            console.error('Error fetching packages:', error);
            listErrorMsg.textContent = `Error: ${error.message}`;
        } finally {
            listLoadingMsg.style.display = 'none';
        }
    }

    // Function to handle publish form submission
    async function handlePublishSubmit(event) {
        event.preventDefault(); // Prevent default form submission

        publishStatusMsg.textContent = 'Publishing...';
        publishErrorMsg.textContent = '';

        const packageFile = packageFileInput.files[0];
        const metadataValue = metadataInput.value;

        if (!packageFile) {
            publishErrorMsg.textContent = 'Please select a package file.';
            publishStatusMsg.textContent = '';
            return;
        }
        if (!metadataValue) {
            publishErrorMsg.textContent = 'Please provide metadata JSON.';
            publishStatusMsg.textContent = '';
            return;
        }

        // Validate metadata is parseable JSON before sending (basic check)
        try {
            JSON.parse(metadataValue);
        } catch (e) {
            publishErrorMsg.textContent = 'Metadata is not valid JSON.';
            publishStatusMsg.textContent = '';
            return;
        }

        const formData = new FormData();
        formData.append('package', packageFile);
        formData.append('metadata', metadataValue);

        try {
            const response = await fetch(`${API_PACKAGE_BASE_URL}/publish`, {
                method: 'POST',
                body: formData, // FormData sets Content-Type automatically to multipart/form-data
            });

            const result = await response.json();

            if (!response.ok) {
                 throw new Error(`Publish failed: ${response.status} ${response.statusText} - ${result.details || result.error}`);
            }

            publishStatusMsg.textContent = `Success: ${result.message} (Name: ${result.name}, Version: ${result.version})`;
            publishForm.reset(); // Clear the form
            // Refresh the package list after successful publish
            fetchAndDisplayPackages();

        } catch (error) {
            console.error('Error publishing package:', error);
            publishErrorMsg.textContent = `Error: ${error.message}`;
            publishStatusMsg.textContent = '';
        }
    }

    // --- Server Functions (New) ---

    // Function to fetch and display registered servers
    async function fetchAndDisplayServers() {
        serverListLoadingMsg.style.display = 'block';
        serverListErrorMsg.textContent = '';
        serverListEl.innerHTML = ''; // Clear previous list

        try {
            const response = await fetch(`${API_SERVER_BASE_URL}`);
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(`Failed to fetch servers: ${response.status} ${response.statusText} - ${errorData.details || errorData.error}`);
            }
            const servers = await response.json();

            if (servers.length === 0) {
                serverListEl.innerHTML = '<tr><td colspan="5">No servers registered yet.</td></tr>';
            } else {
                servers.forEach(server => {
                    const tr = document.createElement('tr');

                    const nameTd = document.createElement('td');
                    nameTd.innerHTML = `<strong>${server.display_name}</strong> [${server.registry_name}]`;
                    tr.appendChild(nameTd);

                    const urlTd = document.createElement('td');
                    if (server.github_url) {
                        const link = document.createElement('a');
                        link.href = server.github_url;
                        link.textContent = server.github_url;
                        link.target = '_blank'; // Open in new tab
                        urlTd.appendChild(link);
                    } else {
                        urlTd.textContent = 'N/A';
                    }
                    tr.appendChild(urlTd);

                    const langTd = document.createElement('td');
                    langTd.textContent = server.language || 'N/A';
                    tr.appendChild(langTd);

                    const configTd = document.createElement('td');
                    const configPre = document.createElement('pre');
                    configPre.textContent = server.config_command || 'N/A';
                    configTd.appendChild(configPre);
                    tr.appendChild(configTd);

                    const timeTd = document.createElement('td');
                    timeTd.textContent = server.registration_time ? new Date(server.registration_time).toLocaleString() : 'N/A';
                    tr.appendChild(timeTd);

                    const deleteTd = document.createElement('td');
                    const deleteBtn = document.createElement('button');
                    deleteBtn.textContent = 'Delete';
                    deleteBtn.classList.add('delete-server-btn');
                    deleteBtn.setAttribute('data-name', server.registry_name);
                    deleteTd.appendChild(deleteBtn);
                    tr.appendChild(deleteTd);

                    serverListEl.appendChild(tr);
                });
            }
        } catch (error) {
            console.error('Error fetching servers:', error);
            serverListErrorMsg.textContent = `Error: ${error.message}`;
        } finally {
            serverListLoadingMsg.style.display = 'none';
        }
    }

    // Function to handle server registration form submission
    async function handleRegisterServerSubmit(event) {
        event.preventDefault(); // Prevent default form submission

        registerStatusMsg.textContent = 'Registering...';
        registerErrorMsg.textContent = '';

        const serverData = {
            name: serverNameInput.value.trim(),
            github_url: serverGithubUrlInput.value.trim() || null, // Send null if empty
            language: serverLanguageInput.value || null, // Send null if empty
            config_command: serverConfigInput.value.trim() || null // Send null if empty (server will use default)
        };

        if (!serverData.name) {
            registerErrorMsg.textContent = 'Server Name is required.';
            registerStatusMsg.textContent = '';
            return;
        }

        try {
            const response = await fetch(`${API_SERVER_BASE_URL}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(serverData),
            });

            const result = await response.json();

            if (!response.ok) {
                 throw new Error(`Registration failed: ${response.status} ${response.statusText} - ${result.details || result.error}`);
            }

            registerStatusMsg.textContent = `Success: ${result.message} (Name: ${result.name})`;
            registerServerForm.reset(); // Clear the form
            // Refresh the server list after successful registration
            fetchAndDisplayServers();

        } catch (error) {
            console.error('Error registering server:', error);
            registerErrorMsg.textContent = `Error: ${error.message}`;
            registerStatusMsg.textContent = '';
        }
    }

    // --- Delete Functions ---

    async function deleteServer(serverRegistryName) { 
        if (!confirm(`Are you sure you want to delete the server with registry name '${serverRegistryName}'? This cannot be undone.`)) {
            return;
        }
        try {
            const response = await fetch(`${API_SERVER_BASE_URL}/${serverRegistryName}`, { 
                method: 'DELETE',
            });
            const result = await response.json();
            if (!response.ok) {
                throw new Error(result.message || `Failed to delete server (HTTP ${response.status})`);
            }
            alert(result.message); // Show success message
            fetchAndDisplayServers(); // Refresh the list
        } catch (error) {
            console.error('Error deleting server:', error);
            alert(`Error deleting server: ${error.message}`);
        }
    }

    async function deletePackage(packageName) {
        if (!confirm(`Are you sure you want to delete the package '${packageName}' and all its versions/files? This cannot be undone.`)) {
            return;
        }
        try {
            const response = await fetch(`${API_PACKAGE_BASE_URL}/${packageName}`, {
                method: 'DELETE',
            });
            const result = await response.json();
            if (!response.ok) {
                throw new Error(result.message || `Failed to delete package (HTTP ${response.status})`);
            }
            alert(result.message); // Show success message
            fetchAndDisplayPackages(); // Refresh the list
        } catch (error) {
            console.error('Error deleting package:', error);
            alert(`Error deleting package: ${error.message}`);
        }
    }

    // --- Attach Event Listeners ---
    publishForm.addEventListener('submit', handlePublishSubmit);
    registerServerForm.addEventListener('submit', handleRegisterServerSubmit); // New listener

    // Add event listeners for delete buttons using event delegation
    serverListEl.addEventListener('click', (event) => {
        if (event.target.classList.contains('delete-server-btn')) {
            const serverName = event.target.getAttribute('data-name');
            if (serverName) {
                deleteServer(serverName);
            }
        }
    });

    packageListEl.addEventListener('click', (event) => {
        if (event.target.classList.contains('delete-package-btn')) {
            const packageName = event.target.getAttribute('data-name');
            if (packageName) {
                deletePackage(packageName);
            }
        }
    });

    // --- Initial Data Load ---
    fetchAndDisplayPackages();
    fetchAndDisplayServers(); // New initial load
});

// --- Utility Functions ---
