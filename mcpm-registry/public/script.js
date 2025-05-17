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

    // --- Delete Functions ---

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
    // Only add listeners if the forms exist on the current page
    if (publishForm) {
        publishForm.addEventListener('submit', handlePublishSubmit);
    }

    if (packageListEl) {
        packageListEl.addEventListener('click', (event) => {
            if (event.target.classList.contains('delete-package-btn')) {
                const packageName = event.target.getAttribute('data-name');
                if (packageName) {
                    deletePackage(packageName);
                }
            }
        });
    }

    // --- Initial Data Load ---
    fetchAndDisplayPackages();
    fetchAndDisplayServers(); // New initial load

    // Make loadServerForEditing globally accessible for the inline script in edit-server.html
    // Needs to be inside the DOMContentLoaded listener where the function is defined.
    window.loadServerForEditing = loadServerForEditing;

}); // End of DOMContentLoaded listener

// --- Utility Functions ---
// (Moved outside DOMContentLoaded)
