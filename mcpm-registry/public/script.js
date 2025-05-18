// mcpm-registry/public/script.js
document.addEventListener('DOMContentLoaded', () => {
    // --- Package Elements ---
    const packageListEl = document.getElementById('package-list');
    const listLoadingMsg = document.getElementById('list-loading-message');
    const listErrorMsg = document.getElementById('list-error-message');
    const packageSearchInput = document.getElementById('package-search');
    
    // --- Publish Elements ---
    const publishForm = document.getElementById('publish-form');
    const packageFileInput = document.getElementById('package-file');
    const metadataInput = document.getElementById('metadata');
    const publishStatusMsg = document.getElementById('publish-status-message');
    const publishErrorMsg = document.getElementById('publish-error-message');
    
    // --- Registry Info Elements ---
    const registryUrlEl = document.getElementById('registry-url');


    const API_PACKAGE_BASE_URL = '/api/packages'; // Renamed for clarity
    const API_SERVER_BASE_URL = '/api/servers'; // New base URL for servers

    // Get the config command textarea
    const configCommandTextarea = document.getElementById('server-config-command'); // Corrected ID

    // Set the placeholder with newline characters, matching server default
    if (configCommandTextarea) {
         // Match the default structure from server.js, but use placeholder text
         configCommandTextarea.placeholder = '{\n  "mcpServers": {\n    "github": {\n      "command": "npx",\n      "args": [\n        "-y",\n        "@modelcontextprotocol/server-github"\n      ],\n    }\n  }\n}';
    }

    // --- Global variables ---
    let allPackages = []; // Store all packages for filtering
    
    // --- Package Functions ---
    async function fetchAndDisplayPackages() {
        listLoadingMsg.style.display = 'block';
        listErrorMsg.textContent = '';
        packageListEl.innerHTML = ''; // Clear previous list

        try {
            const response = await fetch(`${API_PACKAGE_BASE_URL}/`);
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(`Failed to fetch packages: ${response.status} ${response.statusText} - ${errorData.details || errorData.error}`);
            }
            allPackages = await response.json(); // Store all packages globally
            displayFilteredPackages(); // Display packages (possibly filtered)
        } catch (error) {
            console.error('Error fetching packages:', error);
            listErrorMsg.textContent = `Error: ${error.message}`;
            listErrorMsg.style.display = 'block';
        } finally {
            listLoadingMsg.style.display = 'none';
        }
    }
    
    function displayFilteredPackages(searchTerm = '') {
        // Clear the list
        packageListEl.innerHTML = '';
        
        // Filter packages based on search term
        const filteredPackages = searchTerm
            ? allPackages.filter(pkg => 
                pkg.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                (pkg.description && pkg.description.toLowerCase().includes(searchTerm.toLowerCase()))
              )
            : allPackages;
            
        if (filteredPackages.length === 0) {
            const noResultsMessage = searchTerm
                ? `No packages matching "${searchTerm}" found.`
                : 'No packages found in the registry.';
            packageListEl.innerHTML = `<li class="no-results">${noResultsMessage}</li>`;
        } else {
            filteredPackages.forEach(pkg => {
                const li = document.createElement('li');
                
                // Create package info section
                const infoDiv = document.createElement('div');
                infoDiv.className = 'package-info';
                
                // Format the package name and version
                const nameSpan = document.createElement('span');
                nameSpan.className = 'package-name';
                nameSpan.innerHTML = `<strong>${pkg.name}</strong> `;
                if (pkg.latest_version) {
                    const versionBadge = document.createElement('span');
                    versionBadge.className = 'badge badge-primary';
                    versionBadge.textContent = `v${pkg.latest_version}`;
                    nameSpan.appendChild(versionBadge);
                }
                
                // Add description
                const descP = document.createElement('p');
                descP.className = 'package-description';
                descP.textContent = pkg.description || 'No description available';
                
                // Add package metadata if available
                const metaDiv = document.createElement('div');
                metaDiv.className = 'package-meta';
                if (pkg.author) {
                    const authorSpan = document.createElement('span');
                    authorSpan.innerHTML = `<i class="fas fa-user"></i> ${pkg.author}`;
                    metaDiv.appendChild(authorSpan);
                }
                
                // Assemble the info section
                infoDiv.appendChild(nameSpan);
                infoDiv.appendChild(descP);
                infoDiv.appendChild(metaDiv);
                
                // Create actions section
                const actionsDiv = document.createElement('div');
                actionsDiv.className = 'package-actions';
                
                // Download button
                const downloadBtn = document.createElement('button');
                downloadBtn.className = 'btn btn-sm';
                downloadBtn.innerHTML = `<i class="fas fa-download"></i>`;
                downloadBtn.title = 'Download package';
                downloadBtn.dataset.name = pkg.name;
                downloadBtn.dataset.version = pkg.latest_version || 'latest';
                downloadBtn.addEventListener('click', () => downloadPackage(pkg.name, pkg.latest_version || 'latest'));
                
                // Delete button
                const deleteBtn = document.createElement('button');
                deleteBtn.className = 'btn btn-sm btn-danger';
                deleteBtn.innerHTML = `<i class="fas fa-trash-alt"></i>`;
                deleteBtn.title = 'Delete package';
                deleteBtn.dataset.name = pkg.name;
                deleteBtn.addEventListener('click', () => confirmDeletePackage(pkg.name));
                
                // Add buttons to actions
                actionsDiv.appendChild(downloadBtn);
                actionsDiv.appendChild(deleteBtn);
                
                // Assemble the list item
                li.appendChild(infoDiv);
                li.appendChild(actionsDiv);
                packageListEl.appendChild(li);
            });
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

            if (response.ok) {
                // Show success message with animation
                publishStatusMsg.innerHTML = '<i class="fas fa-check-circle"></i> Package published successfully!';
                publishStatusMsg.style.display = 'block';
                publishForm.reset(); // Reset the form on success
                
                // Add success animation
                publishStatusMsg.classList.add('animate-success');
                setTimeout(() => {
                    publishStatusMsg.classList.remove('animate-success');
                }, 1000);
                
                // Refresh the package list
                fetchAndDisplayPackages();
            } else {
                const errorData = await response.json();
                throw new Error(`Failed to publish package: ${response.status} ${response.statusText} - ${errorData.details || errorData.error}`);
            }
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

    // --- Package Management Functions ---
    
    // Function to download a package
    function downloadPackage(packageName, version) {
        const downloadUrl = `${API_PACKAGE_BASE_URL}/${packageName}/${version}/download`;
        window.open(downloadUrl, '_blank');
    }
    
    // Function to confirm package deletion
    function confirmDeletePackage(packageName) {
        // Create a modal dialog for confirmation
        const modal = document.createElement('div');
        modal.className = 'modal';
        modal.innerHTML = `
            <div class="modal-content">
                <h3>Confirm Deletion</h3>
                <p>Are you sure you want to delete the package <strong>${packageName}</strong>?</p>
                <p class="warning"><i class="fas fa-exclamation-triangle"></i> This action cannot be undone!</p>
                <div class="modal-actions">
                    <button class="btn btn-sm" id="cancel-delete">Cancel</button>
                    <button class="btn btn-sm btn-danger" id="confirm-delete">Delete</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        
        // Add event listeners to buttons
        document.getElementById('cancel-delete').addEventListener('click', () => {
            document.body.removeChild(modal);
        });
        
        document.getElementById('confirm-delete').addEventListener('click', () => {
            document.body.removeChild(modal);
            deletePackage(packageName);
        });
    }
    
    // Function to delete a package
    async function deletePackage(packageName) {
        try {
            const response = await fetch(`${API_PACKAGE_BASE_URL}/${packageName}`, {
                method: 'DELETE'
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(`Failed to delete package: ${response.status} ${response.statusText} - ${errorData.details || errorData.error}`);
            }

            // Show success message
            const successMsg = document.createElement('div');
            successMsg.className = 'toast success-toast';
            successMsg.innerHTML = `<i class="fas fa-check-circle"></i> Package ${packageName} deleted successfully.`;
            document.body.appendChild(successMsg);
            
            // Remove the toast after 3 seconds
            setTimeout(() => {
                document.body.removeChild(successMsg);
            }, 3000);
            
            // Refresh the package list
            fetchAndDisplayPackages();
        } catch (error) {
            console.error('Error deleting package:', error);
            
            // Show error message
            const errorMsg = document.createElement('div');
            errorMsg.className = 'toast error-toast';
            errorMsg.innerHTML = `<i class="fas fa-exclamation-circle"></i> Error: ${error.message}`;
            document.body.appendChild(errorMsg);
            
            // Remove the toast after 5 seconds
            setTimeout(() => {
                document.body.removeChild(errorMsg);
            }, 5000);
        }
    }

    // --- Search Functionality ---
    function handleSearch() {
        const searchTerm = packageSearchInput.value.trim();
        displayFilteredPackages(searchTerm);
    }
    
    // --- Initialize Registry Info ---
    function initializeRegistryInfo() {
        if (registryUrlEl) {
            registryUrlEl.textContent = window.location.origin + '/api';
        }
    }
    
    // --- Attach Event Listeners ---
    // Only add listeners if the elements exist on the current page
    if (publishForm) {
        publishForm.addEventListener('submit', handlePublishSubmit);
    }
    
    if (packageSearchInput) {
        packageSearchInput.addEventListener('input', handleSearch);
    }
    
    // Initialize the page
    initializeRegistryInfo();
    fetchAndDisplayPackages();
    // Only call fetchAndDisplayServers if it exists
    if (typeof fetchAndDisplayServers === 'function') {
        fetchAndDisplayServers();
    }

    // Make loadServerForEditing globally accessible for the inline script in edit-server.html
    // Needs to be inside the DOMContentLoaded listener where the function is defined.
    window.loadServerForEditing = loadServerForEditing;

}); // End of DOMContentLoaded listener

// --- Utility Functions ---
// (Moved outside DOMContentLoaded)
